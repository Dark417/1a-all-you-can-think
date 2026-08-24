import express from 'express';
import { config, isMock, resolveApp, redirectUri } from '../config.js';
import { createPkcePair } from '../auth/pkce.js';
import { txStore, sessionStore, randomId } from '../auth/store.js';
import { buildAuthorizeUrl, buildLogoutUrl, exchangeCode, globalSignOut, metadata, scopes } from '../auth/oidc.js';
import { verifyIdToken, verifyAccessToken, profileFromIdToken } from '../auth/tokens.js';
import {
  requireAuth,
  requireCsrf,
  setSessionCookies,
  clearSessionCookies,
} from '../auth/middleware.js';

export function authRouter() {
  const router = express.Router();

  /**
   * What the UI needs to know before it renders a "Sign in" button. Note what
   * is NOT here: no client secret, no token endpoint, no PKCE material. The
   * browser does not need any of it.
   */
  router.get('/config', (_req, res) => {
    const m = metadata();
    res.json({
      authMode: config.authMode,
      issuer: m.issuer,
      clientId: m.clientId,
      scopes: scopes(),
      redirectUri: redirectUri(),
      loginPath: '/auth/login',
      logoutPath: '/auth/logout',
      apps: Object.keys(config.apps),
    });
  });

  /**
   * STEP 1 - the UI sends the browser here (a full page navigation, not fetch).
   *
   * We mint state + nonce + a PKCE pair, park them server side, and 302 the
   * browser on to Cognito. From here until the callback, AWS is talking to the
   * user directly: the password is typed on an AWS-hosted page and never
   * touches this backend or any of the three frontends.
   */
  router.get('/login', (req, res) => {
    const appName = String(req.query.app ?? '');
    const app = resolveApp(appName);
    if (!app) {
      return res.status(400).json({
        error: 'unknown_app',
        message: `?app= must be one of: ${Object.keys(config.apps).join(', ')}`,
      });
    }

    // Only ever return the user to their own origin - otherwise /auth/login is
    // an open redirect that an attacker can point at their own site.
    const requested = req.query.returnTo ? String(req.query.returnTo) : app.home;
    const returnTo = isSafeReturnTo(requested, app.origin) ? requested : app.home;

    const nonce = randomId(16);
    const { codeVerifier, codeChallenge } = createPkcePair();
    const state = txStore.create({ nonce, codeVerifier, returnTo, app: appName });

    // Bind the transaction to *this* browser, so a code injected into someone
    // else's callback cannot be redeemed.
    res.cookie(config.session.txCookieName, state, {
      httpOnly: true,
      secure: config.session.secure,
      sameSite: config.session.sameSite,
      maxAge: 10 * 60_000,
      path: '/auth',
    });

    res.redirect(buildAuthorizeUrl({ state, nonce, codeChallenge }));
  });

  /**
   * STEP 2 - Cognito sends the browser back here with a one-time code.
   *
   * The redirect URI registered in the user pool points at this backend, not at
   * any of the UIs. That is what lets us keep the code exchange server side.
   */
  router.get('/callback', async (req, res, next) => {
    const fallbackHome = config.apps.react.home;
    try {
      const { code, state, error, error_description: errorDescription } = req.query;

      if (error) {
        return res.redirect(
          failureUrl(fallbackHome, String(error), errorDescription ? String(errorDescription) : undefined),
        );
      }
      if (!code || !state) return res.redirect(failureUrl(fallbackHome, 'missing_code'));

      const boundState = req.cookies?.[config.session.txCookieName];
      res.clearCookie(config.session.txCookieName, { path: '/auth' });
      if (!boundState || boundState !== state) {
        return res.redirect(failureUrl(fallbackHome, 'state_mismatch'));
      }

      const tx = txStore.take(String(state));
      if (!tx) return res.redirect(failureUrl(fallbackHome, 'login_expired'));

      const app = resolveApp(tx.app) ?? config.apps.react;

      // STEP 3 - back channel. Code + PKCE verifier -> tokens.
      const tokens = await exchangeCode({ code: String(code), codeVerifier: tx.codeVerifier });

      // Verify before trusting, even though we just fetched them ourselves.
      const idClaims = await verifyIdToken(tokens.id_token, { nonce: tx.nonce });
      await verifyAccessToken(tokens.access_token);

      const csrfToken = randomId(24);
      const sid = sessionStore.create({
        profile: profileFromIdToken(idClaims),
        accessToken: tokens.access_token,
        idToken: tokens.id_token,
        refreshToken: tokens.refresh_token ?? null,
        accessTokenExpiresAt: Date.now() + (tokens.expires_in ?? 3600) * 1000,
        csrfToken,
        app: tx.app,
      });

      setSessionCookies(res, { sid, csrfToken });
      res.redirect(tx.returnTo ?? app.home);
    } catch (err) {
      if (err.oauthError || err.status === 400) {
        return res.redirect(failureUrl(fallbackHome, err.oauthError ?? 'token_exchange_failed', err.message));
      }
      next(err);
    }
  });

  /** Who am I? The only "auth" call the UIs make on load. */
  router.get('/session', requireAuth, (req, res) => {
    const session = req.auth.sid ? sessionStore.get(req.auth.sid) : null;
    res.json({
      authenticated: true,
      via: req.auth.via,
      user: req.auth.profile,
      // Handy while learning; you would not ship token internals to the browser.
      token: {
        expiresAt: session ? new Date(session.accessTokenExpiresAt).toISOString() : null,
        expiresInSeconds: session
          ? Math.max(0, Math.round((session.accessTokenExpiresAt - Date.now()) / 1000))
          : null,
        issuer: req.auth.claims.iss,
        scope: req.auth.claims.scope ?? null,
        refreshedAt: session?.refreshedAt ? new Date(session.refreshedAt).toISOString() : null,
      },
    });
  });

  /**
   * Mock-mode only: hand back the raw tokens so you can paste them into
   * jwt.io, or drive the Bearer-token path from curl. This route does not
   * exist when AUTH_MODE=cognito - a browser app has no business seeing these.
   */
  router.get('/debug/tokens', requireAuth, (req, res) => {
    if (!isMock()) return res.status(404).json({ error: 'not_found' });
    const session = req.auth.sid ? sessionStore.get(req.auth.sid) : null;
    if (!session) return res.status(400).json({ error: 'no_session' });
    res.json({
      access_token: session.accessToken,
      id_token: session.idToken,
      refresh_token: session.refreshToken,
      access_token_claims: req.auth.claims,
    });
  });

  /** Force a refresh. Normally unnecessary - the auth middleware does it for you. */
  router.post('/refresh', requireCsrf, requireAuth, (req, res) => {
    const session = req.auth.sid ? sessionStore.get(req.auth.sid) : null;
    if (!session) return res.status(400).json({ error: 'no_session' });
    sessionStore.update(req.auth.sid, { accessTokenExpiresAt: 0 }); // forces renew on next request
    res.json({ ok: true, message: 'Access token will be renewed on the next API call.' });
  });

  /**
   * STEP 4 - logout, all three layers of it:
   *   1. destroy our session (the cookie stops working),
   *   2. GlobalSignOut via the AWS SDK (issued refresh tokens stop working),
   *   3. redirect to the Hosted UI /logout (the AWS SSO cookie is cleared, so
   *      the next login actually prompts instead of silently signing back in).
   */
  router.get('/logout', async (req, res, next) => {
    try {
      const sid = req.cookies?.[config.session.cookieName];
      const session = sessionStore.get(sid);
      const appName = String(req.query.app ?? session?.app ?? 'react');

      if (session) {
        await globalSignOut({ accessToken: session.accessToken, sub: session.profile.sub });
        sessionStore.destroy(sid);
      }
      clearSessionCookies(res);

      // Remember where to land after the IdP bounces us back.
      res.cookie('post_logout_app', appName, {
        httpOnly: true,
        secure: config.session.secure,
        sameSite: config.session.sameSite,
        maxAge: 5 * 60_000,
        path: '/auth',
      });
      res.redirect(buildLogoutUrl());
    } catch (err) {
      next(err);
    }
  });

  router.get('/logout/callback', (req, res) => {
    const appName = req.cookies?.post_logout_app ?? 'react';
    res.clearCookie('post_logout_app', { path: '/auth' });
    const app = resolveApp(appName) ?? config.apps.react;
    clearSessionCookies(res);
    res.redirect(`${app.home}?signed_out=1`);
  });

  return router;
}

function isSafeReturnTo(candidate, origin) {
  try {
    return new URL(candidate).origin === new URL(origin).origin;
  } catch {
    return false;
  }
}

function failureUrl(home, error, description) {
  const url = new URL(home);
  url.searchParams.set('auth_error', error);
  if (description) url.searchParams.set('auth_error_description', description);
  return url.toString();
}
