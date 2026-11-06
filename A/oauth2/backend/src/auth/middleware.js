import { config } from '../config.js';
import { sessionStore } from './store.js';
import { refreshTokens } from './oidc.js';
import { verifyAccessToken, verifyIdToken, profileFromIdToken } from './tokens.js';

const REFRESH_SKEW_MS = 60_000; // refresh a minute before the token actually expires

/**
 * Resolve the caller.
 *
 * Two accepted credentials, one verification path:
 *   1. the httpOnly session cookie the browser apps use (BFF pattern), or
 *   2. `Authorization: Bearer <access token>` for a mobile app, a CLI or a
 *      service-to-service caller that has no cookie jar.
 *
 * Either way we end up verifying a Cognito access token against the JWKS.
 */
export function requireAuth(req, res, next) {
  resolveIdentity(req, res)
    .then((identity) => {
      if (!identity) {
        return res.status(401).json({ error: 'unauthenticated', message: 'Sign in to continue.' });
      }
      req.auth = identity;
      next();
    })
    .catch(next);
}

/** Same as requireAuth but lets anonymous callers through with req.auth = null. */
export function optionalAuth(req, res, next) {
  resolveIdentity(req, res)
    .then((identity) => {
      req.auth = identity;
      next();
    })
    .catch(() => {
      req.auth = null;
      next();
    });
}

async function resolveIdentity(req, res) {
  const bearer = req.get('authorization');
  if (bearer?.toLowerCase().startsWith('bearer ')) {
    const token = bearer.slice(7).trim();
    try {
      const claims = await verifyAccessToken(token);
      return {
        via: 'bearer',
        sid: null,
        profile: {
          sub: claims.sub,
          username: claims.username ?? claims.sub,
          email: null,
          name: claims.username ?? null,
          groups: claims['cognito:groups'] ?? [],
        },
        accessToken: token,
        claims,
      };
    } catch {
      return null;
    }
  }

  const sid = req.cookies?.[config.session.cookieName];
  let session = sessionStore.get(sid);
  if (!session) return null;

  // Transparent refresh: the UIs never think about token lifetimes.
  if (session.accessTokenExpiresAt - REFRESH_SKEW_MS < Date.now()) {
    session = await renew(sid, session, res);
    if (!session) return null;
  }

  let claims;
  try {
    claims = await verifyAccessToken(session.accessToken);
  } catch {
    sessionStore.destroy(sid);
    clearSessionCookies(res);
    return null;
  }

  return { via: 'session', sid, profile: session.profile, accessToken: session.accessToken, claims };
}

async function renew(sid, session, res) {
  if (!session.refreshToken) {
    sessionStore.destroy(sid);
    clearSessionCookies(res);
    return null;
  }
  try {
    const tokens = await refreshTokens(session.refreshToken);
    const idClaims = tokens.id_token ? await verifyIdToken(tokens.id_token) : null;
    return sessionStore.update(sid, {
      accessToken: tokens.access_token,
      idToken: tokens.id_token ?? session.idToken,
      // Cognito does not rotate refresh tokens; keep the one we have if none comes back.
      refreshToken: tokens.refresh_token ?? session.refreshToken,
      accessTokenExpiresAt: Date.now() + (tokens.expires_in ?? 3600) * 1000,
      profile: idClaims ? profileFromIdToken(idClaims) : session.profile,
      refreshedAt: Date.now(),
    });
  } catch {
    // Refresh token expired or was revoked -> the session is over.
    sessionStore.destroy(sid);
    clearSessionCookies(res);
    return null;
  }
}

/**
 * Double-submit CSRF check.
 *
 * Cookie auth means the browser attaches credentials automatically, including
 * on requests a third-party site triggered. SameSite=Lax blocks the obvious
 * cases but is not a complete defence, so every state-changing request must
 * echo the csrf cookie back in a header - something a cross-origin page cannot
 * read. Bearer callers are exempt: nothing is attached automatically for them.
 */
export function requireCsrf(req, res, next) {
  if (['GET', 'HEAD', 'OPTIONS'].includes(req.method)) return next();
  if (req.get('authorization')) return next();

  const cookieToken = req.cookies?.[config.session.csrfCookieName];
  const headerToken = req.get('x-csrf-token');
  if (!cookieToken || !headerToken || cookieToken !== headerToken) {
    return res.status(403).json({ error: 'csrf_failed', message: 'Missing or invalid CSRF token.' });
  }
  next();
}

/** Coarse role check driven by Cognito groups. */
export function requireGroup(...groups) {
  return (req, res, next) => {
    const mine = req.auth?.profile?.groups ?? [];
    if (groups.some((g) => mine.includes(g))) return next();
    res.status(403).json({
      error: 'forbidden',
      message: `Requires one of: ${groups.join(', ')}. You have: ${mine.join(', ') || 'none'}.`,
    });
  };
}

export function setSessionCookies(res, { sid, csrfToken }) {
  const { cookieName, csrfCookieName, secure, sameSite, ttlSeconds } = config.session;
  const maxAge = ttlSeconds * 1000;
  // httpOnly: JavaScript must never be able to read this. That is the whole
  // point of keeping tokens out of localStorage.
  res.cookie(cookieName, sid, { httpOnly: true, secure, sameSite, maxAge, path: '/' });
  // Deliberately readable by JS - the UI has to copy it into a header.
  res.cookie(csrfCookieName, csrfToken, { httpOnly: false, secure, sameSite, maxAge, path: '/' });
}

export function clearSessionCookies(res) {
  const { cookieName, csrfCookieName, secure, sameSite } = config.session;
  res.clearCookie(cookieName, { httpOnly: true, secure, sameSite, path: '/' });
  res.clearCookie(csrfCookieName, { httpOnly: false, secure, sameSite, path: '/' });
}
