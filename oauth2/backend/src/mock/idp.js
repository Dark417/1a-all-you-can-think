import crypto from 'node:crypto';
import express from 'express';
import { SignJWT, exportJWK, generateKeyPair } from 'jose';
import { config } from '../config.js';
import { MOCK_USERS, findMockUser } from './users.js';

/**
 * A local stand-in for the AWS Cognito Hosted UI.
 *
 * It is deliberately a *real* OIDC provider rather than a stub:
 *   - publishes /.well-known/openid-configuration and a JWKS
 *   - enforces PKCE (S256)
 *   - signs real RS256 JWTs whose claims match Cognito's shape
 *     (token_use, client_id, cognito:groups, ...)
 *
 * That matters: the backend verifies tokens with jose + a remote JWKS, and it
 * runs the exact same code path against this mock as it does against AWS. So a
 * flow that works locally works against a real user pool.
 */

const ISSUER = () => `${config.baseUrl}/mock-idp`;
const ACCESS_TTL = 300; // seconds - deliberately short so refresh is easy to demo
const ID_TTL = 300;
const REFRESH_TTL = 60 * 60 * 24;

let keys = null;
async function getKeys() {
  if (keys) return keys;
  const { publicKey, privateKey } = await generateKeyPair('RS256', { extractable: true });
  const jwk = await exportJWK(publicKey);
  jwk.kid = 'mock-key-1';
  jwk.use = 'sig';
  jwk.alg = 'RS256';
  keys = { privateKey, jwk };
  return keys;
}

/** code -> { user, codeChallenge, nonce, redirectUri, clientId, scope, expiresAt } */
const codes = new Map();
/** refresh token -> { sub, clientId, scope, expiresAt } */
const refreshTokens = new Map();
/** Very small "the browser is already signed in to the IdP" session. */
const idpSessions = new Map();

const now = () => Math.floor(Date.now() / 1000);
const rand = (n = 32) => crypto.randomBytes(n).toString('base64url');

function sweep() {
  const t = now();
  for (const [k, v] of codes) if (v.expiresAt < t) codes.delete(k);
  for (const [k, v] of refreshTokens) if (v.expiresAt < t) refreshTokens.delete(k);
  for (const [k, v] of idpSessions) if (v.expiresAt < t) idpSessions.delete(k);
}
setInterval(sweep, 60_000).unref();

const s256 = (verifier) => crypto.createHash('sha256').update(verifier).digest('base64url');

async function signAccessToken(user, clientId, scope) {
  const { privateKey, jwk } = await getKeys();
  return new SignJWT({
    token_use: 'access',
    client_id: clientId,
    scope,
    username: user.username,
    'cognito:groups': user.groups,
    jti: crypto.randomUUID(),
  })
    .setProtectedHeader({ alg: 'RS256', kid: jwk.kid })
    .setIssuer(ISSUER())
    .setSubject(user.sub)
    .setIssuedAt()
    .setExpirationTime(`${ACCESS_TTL}s`)
    .sign(privateKey);
}

async function signIdToken(user, clientId, nonce) {
  const { privateKey, jwk } = await getKeys();
  return new SignJWT({
    token_use: 'id',
    email: user.email,
    email_verified: true,
    name: user.name,
    'cognito:username': user.username,
    'cognito:groups': user.groups,
    auth_time: now(),
    ...(nonce ? { nonce } : {}),
  })
    .setProtectedHeader({ alg: 'RS256', kid: jwk.kid })
    .setIssuer(ISSUER())
    .setAudience(clientId)
    .setSubject(user.sub)
    .setIssuedAt()
    .setExpirationTime(`${ID_TTL}s`)
    .sign(privateKey);
}

const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

function loginPage({ query, error }) {
  const hidden = Object.entries(query)
    .map(([k, v]) => `<input type="hidden" name="${esc(k)}" value="${esc(v)}">`)
    .join('\n      ');
  const shortcuts = MOCK_USERS.map(
    (u) => `<button class="who" type="submit" name="username" value="${esc(u.username)}">
        <strong>${esc(u.username)}</strong><span>${esc(u.groups.join(', '))}</span></button>`,
  ).join('\n      ');

  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sign in - Mock Cognito</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%23ff9900'/%3E%3Cpath d='M11 14v-2.5a5 5 0 0 1 10 0V14h1.2v9.5H9.8V14H11zm2 0h6v-2.5a3 3 0 0 0-6 0V14z' fill='%2316191f'/%3E%3C/svg%3E">
<style>
  :root { color-scheme: light dark; --fg:#0f172a; --bg:#f1f5f9; --card:#fff; --line:#cbd5e1; --accent:#ff9900; }
  @media (prefers-color-scheme: dark){ :root{ --fg:#e2e8f0; --bg:#0b1220; --card:#131c31; --line:#334155; } }
  *{box-sizing:border-box} body{margin:0;min-height:100vh;display:grid;place-items:center;
    background:var(--bg);color:var(--fg);font:15px/1.5 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
  .card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:28px;width:min(400px,92vw);
    box-shadow:0 10px 30px rgba(2,6,23,.10)}
  h1{font-size:17px;margin:0 0 4px} p.sub{margin:0 0 20px;opacity:.7;font-size:13px}
  label{display:block;font-size:12px;font-weight:600;margin:12px 0 5px;letter-spacing:.02em;text-transform:uppercase;opacity:.75}
  input[type=text],input[type=password]{width:100%;padding:10px 12px;border:1px solid var(--line);border-radius:8px;
    background:transparent;color:inherit;font-size:14px}
  button.primary{width:100%;margin-top:20px;padding:11px;border:0;border-radius:8px;background:var(--accent);
    color:#1a1a1a;font-weight:700;font-size:14px;cursor:pointer}
  .who{display:flex;flex-direction:column;align-items:flex-start;gap:2px;flex:1;padding:8px 10px;cursor:pointer;
    border:1px dashed var(--line);border-radius:8px;background:transparent;color:inherit;font:inherit}
  .who span{font-size:11px;opacity:.6} .row{display:flex;gap:8px;margin-top:8px}
  .err{background:#fee2e2;color:#991b1b;border-radius:8px;padding:8px 10px;font-size:13px;margin-bottom:12px}
  .hint{margin-top:18px;font-size:11px;opacity:.6;text-align:center}
</style></head>
<body>
  <div class="card">
    <h1>Mock Cognito Hosted UI</h1>
    <p class="sub">Stands in for <code>https://&lt;domain&gt;.auth.&lt;region&gt;.amazoncognito.com</code></p>
    ${error ? `<div class="err">${esc(error)}</div>` : ''}
    <form method="post" action="${esc(config.baseUrl)}/mock-idp/login">
      ${hidden}
      <label for="username">Username</label>
      <input id="username" name="username" type="text" autocomplete="username" value="alice" required>
      <label for="password">Password</label>
      <input id="password" name="password" type="password" autocomplete="current-password" value="Password1!" required>
      <button class="primary" type="submit">Sign in</button>
      <div class="row">${shortcuts}</div>
    </form>
    <p class="hint">Any listed user, password <code>Password1!</code></p>
  </div>
</body></html>`;
}

export function mockIdpRouter() {
  const router = express.Router();
  router.use(express.urlencoded({ extended: false }));

  router.get('/.well-known/openid-configuration', (_req, res) => {
    const issuer = ISSUER();
    res.json({
      issuer,
      authorization_endpoint: `${issuer}/authorize`,
      token_endpoint: `${issuer}/token`,
      jwks_uri: `${issuer}/.well-known/jwks.json`,
      end_session_endpoint: `${issuer}/logout`,
      userinfo_endpoint: `${issuer}/userInfo`,
      response_types_supported: ['code'],
      grant_types_supported: ['authorization_code', 'refresh_token'],
      id_token_signing_alg_values_supported: ['RS256'],
      code_challenge_methods_supported: ['S256'],
      scopes_supported: ['openid', 'email', 'profile'],
    });
  });

  router.get('/.well-known/jwks.json', async (_req, res) => {
    const { jwk } = await getKeys();
    res.json({ keys: [jwk] });
  });

  // ---- authorization endpoint -------------------------------------------------
  router.get('/authorize', (req, res) => {
    const q = req.query;
    if (q.response_type !== 'code') return res.status(400).send('unsupported response_type');
    if (!q.client_id || !q.redirect_uri) return res.status(400).send('missing client_id/redirect_uri');
    if (q.code_challenge_method !== 'S256') return res.status(400).send('PKCE S256 required');

    // Already signed in at the IdP? Skip the form, like a real SSO session would.
    const sid = req.cookies?.mock_idp_session;
    const existing = sid && idpSessions.get(sid);
    if (existing && q.prompt !== 'login') {
      const user = MOCK_USERS.find((u) => u.sub === existing.sub);
      if (user) return issueCode(res, user, q);
    }
    res.type('html').send(loginPage({ query: q, error: null }));
  });

  router.post('/login', (req, res) => {
    const { username, password, ...q } = req.body ?? {};
    // The quick-pick buttons post only a username.
    const user = findMockUser(username, password === undefined || password === '' ? undefined : password);
    if (!user) return res.status(401).type('html').send(loginPage({ query: q, error: 'Incorrect username or password.' }));

    const sid = rand(24);
    idpSessions.set(sid, { sub: user.sub, expiresAt: now() + REFRESH_TTL });
    res.cookie('mock_idp_session', sid, { httpOnly: true, sameSite: 'lax', path: '/mock-idp' });
    issueCode(res, user, q);
  });

  function issueCode(res, user, q) {
    const code = rand(24);
    codes.set(code, {
      sub: user.sub,
      clientId: q.client_id,
      redirectUri: q.redirect_uri,
      codeChallenge: q.code_challenge,
      nonce: q.nonce,
      scope: q.scope ?? 'openid',
      expiresAt: now() + 60,
    });
    const url = new URL(q.redirect_uri);
    url.searchParams.set('code', code);
    if (q.state) url.searchParams.set('state', q.state);
    res.redirect(url.toString());
  }

  // ---- token endpoint ---------------------------------------------------------
  router.post('/token', async (req, res) => {
    const body = req.body ?? {};
    const grant = body.grant_type;

    if (grant === 'authorization_code') {
      const entry = codes.get(body.code);
      codes.delete(body.code); // single use
      if (!entry || entry.expiresAt < now()) return res.status(400).json({ error: 'invalid_grant' });
      if (entry.redirectUri !== body.redirect_uri) return res.status(400).json({ error: 'invalid_grant', error_description: 'redirect_uri mismatch' });
      if (!body.code_verifier || s256(body.code_verifier) !== entry.codeChallenge)
        return res.status(400).json({ error: 'invalid_grant', error_description: 'PKCE verification failed' });

      const user = MOCK_USERS.find((u) => u.sub === entry.sub);
      const refresh = rand(32);
      refreshTokens.set(refresh, {
        sub: user.sub, clientId: entry.clientId, scope: entry.scope, expiresAt: now() + REFRESH_TTL,
      });
      return res.json({
        token_type: 'Bearer',
        expires_in: ACCESS_TTL,
        access_token: await signAccessToken(user, entry.clientId, entry.scope),
        id_token: await signIdToken(user, entry.clientId, entry.nonce),
        refresh_token: refresh,
      });
    }

    if (grant === 'refresh_token') {
      const entry = refreshTokens.get(body.refresh_token);
      if (!entry || entry.expiresAt < now()) return res.status(400).json({ error: 'invalid_grant' });
      const user = MOCK_USERS.find((u) => u.sub === entry.sub);
      // Cognito does not rotate refresh tokens and returns no new one here.
      return res.json({
        token_type: 'Bearer',
        expires_in: ACCESS_TTL,
        access_token: await signAccessToken(user, entry.clientId, entry.scope),
        id_token: await signIdToken(user, entry.clientId, undefined),
      });
    }

    res.status(400).json({ error: 'unsupported_grant_type' });
  });

  // ---- logout -----------------------------------------------------------------
  router.get('/logout', (req, res) => {
    const sid = req.cookies?.mock_idp_session;
    if (sid) idpSessions.delete(sid);
    res.clearCookie('mock_idp_session', { path: '/mock-idp' });
    const target = req.query.logout_uri || req.query.redirect_uri;
    if (target) return res.redirect(String(target));
    res.type('html').send('<p>Signed out of the mock IdP.</p>');
  });

  return router;
}

/** Used by /auth/logout to drop the mock IdP's own refresh tokens for a user. */
export function mockRevokeUser(sub) {
  for (const [k, v] of refreshTokens) if (v.sub === sub) refreshTokens.delete(k);
  for (const [k, v] of idpSessions) if (v.sub === sub) idpSessions.delete(k);
}
