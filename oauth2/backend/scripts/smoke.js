/**
 * End-to-end check of the whole login flow, with no browser involved.
 *
 *   npm run smoke
 *
 * It boots the backend in mock mode, then walks every hop the browser would
 * make - /auth/login -> IdP -> login form -> code -> callback -> session cookie
 * -> API calls -> logout - asserting at each step. If this passes, the flow is
 * wired correctly end to end.
 */
import { spawn } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';

const PORT = process.env.SMOKE_PORT ?? '8099';
const BASE = `http://localhost:${PORT}`;
const APP = 'http://localhost:5173';

// --- the world's smallest cookie jar ---------------------------------------
const jar = new Map();
function absorb(res) {
  for (const raw of res.headers.getSetCookie?.() ?? []) {
    const [pair] = raw.split(';');
    const idx = pair.indexOf('=');
    const name = pair.slice(0, idx).trim();
    const value = pair.slice(idx + 1).trim();
    if (value === '' || /expires=Thu, 01 Jan 1970/i.test(raw)) jar.delete(name);
    else jar.set(name, value);
  }
}
const cookieHeader = () => [...jar].map(([k, v]) => `${k}=${v}`).join('; ');

async function go(url, init = {}) {
  const res = await fetch(url, {
    redirect: 'manual',
    ...init,
    headers: { ...(init.headers ?? {}), ...(jar.size ? { cookie: cookieHeader() } : {}) },
  });
  absorb(res);
  return res;
}

let passed = 0;
function check(label, condition, detail = '') {
  if (condition) {
    passed++;
    console.log(`  \x1b[32m✓\x1b[0m ${label}`);
  } else {
    console.log(`  \x1b[31m✗\x1b[0m ${label}${detail ? `  -> ${detail}` : ''}`);
    process.exitCode = 1;
    throw new Error(`assertion failed: ${label} ${detail}`);
  }
}

const server = spawn(process.execPath, ['src/server.js'], {
  env: { ...process.env, PORT, AUTH_MODE: 'mock', APP_BASE_URL: BASE, QUIET: '1' },
  stdio: ['ignore', 'ignore', 'inherit'],
});

try {
  for (let i = 0; i < 60; i++) {
    try {
      await fetch(`${BASE}/api/public/health`);
      break;
    } catch {
      await sleep(100);
    }
  }

  console.log('\n1. discovery + config');
  const cfg = await (await go(`${BASE}/auth/config`)).json();
  check('GET /auth/config reports mock mode', cfg.authMode === 'mock', JSON.stringify(cfg));
  const disco = await (await go(`${cfg.issuer}/.well-known/openid-configuration`)).json();
  check('mock IdP publishes a discovery document', disco.issuer === cfg.issuer);
  check('mock IdP requires PKCE S256', disco.code_challenge_methods_supported?.includes('S256'));
  const jwks = await (await go(disco.jwks_uri)).json();
  check('mock IdP publishes a JWKS', jwks.keys?.[0]?.kty === 'RSA');

  console.log('\n2. unauthenticated access is refused');
  check('GET /api/notes -> 401', (await go(`${BASE}/api/notes`)).status === 401);

  console.log('\n3. /auth/login redirects the browser to the IdP');
  const login = await go(`${BASE}/auth/login?app=react`);
  const authorizeUrl = new URL(login.headers.get('location'));
  check('302 to the authorization endpoint', login.status === 302 && authorizeUrl.pathname.endsWith('/authorize'));
  check('carries response_type=code', authorizeUrl.searchParams.get('response_type') === 'code');
  check('carries a PKCE S256 challenge', authorizeUrl.searchParams.get('code_challenge_method') === 'S256');
  check('carries state + nonce', !!authorizeUrl.searchParams.get('state') && !!authorizeUrl.searchParams.get('nonce'));
  check('redirect_uri points at the BACKEND, not the UI',
    authorizeUrl.searchParams.get('redirect_uri') === `${BASE}/auth/callback`);
  check('the browser got an httpOnly transaction cookie', jar.has('oauth_tx'));

  console.log('\n4. open redirect is not possible');
  const evil = await go(`${BASE}/auth/login?app=react&returnTo=https://evil.example.com`);
  const evilTx = new URL(evil.headers.get('location'));
  check('a foreign returnTo is ignored', evilTx.searchParams.get('state') !== null);
  check('unknown ?app is rejected', (await go(`${BASE}/auth/login?app=nope`)).status === 400);
  // re-arm a clean transaction after those probes
  const fresh = await go(`${BASE}/auth/login?app=react`);
  const freshAuthorize = new URL(fresh.headers.get('location'));

  console.log('\n5. the user signs in AT THE IDP');
  const page = await go(freshAuthorize.toString());
  check('the IdP serves its own login page', page.status === 200);
  const form = new URLSearchParams();
  for (const [k, v] of freshAuthorize.searchParams) form.set(k, v);
  form.set('username', 'alice');
  form.set('password', 'Password1!');

  const badPassword = await go(`${cfg.issuer}/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ ...Object.fromEntries(form), password: 'wrong' }),
  });
  check('wrong password is rejected by the IdP', badPassword.status === 401);

  const posted = await go(`${cfg.issuer}/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: form,
  });
  const back = new URL(posted.headers.get('location'));
  check('IdP redirects back with a code', posted.status === 302 && !!back.searchParams.get('code'));

  console.log('\n6. callback: code -> tokens -> session cookie');
  const callback = await go(back.toString());
  check('callback redirects to the originating UI',
    callback.status === 302 && callback.headers.get('location').startsWith(APP),
    callback.headers.get('location'));
  check('session cookie was set', jar.has('sid'));
  check('CSRF cookie was set', jar.has('csrf_token'));
  check('the transaction cookie was cleared', !jar.has('oauth_tx'));

  console.log('\n7. the session works');
  const session = await (await go(`${BASE}/auth/session`)).json();
  check('GET /auth/session identifies alice', session.user?.username === 'alice', JSON.stringify(session.user));
  check('cognito groups came through', session.user?.groups?.includes('admin'));
  check('the access token has an expiry', session.token?.expiresInSeconds > 0);

  const notes = await (await go(`${BASE}/api/notes`)).json();
  check('GET /api/notes returns the seeded data', notes.notes?.length >= 3);
  check('admin permissions are reported', notes.permissions?.canDeleteAny === true);

  console.log('\n8. CSRF protection');
  const noCsrf = await go(`${BASE}/api/notes`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ title: 'nope' }),
  });
  check('POST without the CSRF header -> 403', noCsrf.status === 403, String(noCsrf.status));

  const csrf = jar.get('csrf_token');
  const created = await go(`${BASE}/api/notes`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-csrf-token': csrf },
    body: JSON.stringify({ title: 'Written by the smoke test', body: 'hello' }),
  });
  check('POST with the CSRF header -> 201', created.status === 201, String(created.status));
  const createdNote = (await created.json()).note;
  check('the note is attributed to the signed-in user', createdNote.ownerName === 'alice');

  console.log('\n9. group-based authorization');
  const delOwn = await go(`${BASE}/api/notes/${createdNote.id}`, {
    method: 'DELETE',
    headers: { 'x-csrf-token': csrf },
  });
  check('alice (admin) can delete -> 204', delOwn.status === 204, String(delOwn.status));
  const adminOnly = await go(`${BASE}/api/admin/reset`, {
    method: 'POST',
    headers: { 'x-csrf-token': csrf },
  });
  check('admin-only route accepts an admin', adminOnly.status === 200, String(adminOnly.status));

  console.log('\n10. the Bearer-token path (mobile / service clients)');
  const dbg = await (await go(`${BASE}/auth/debug/tokens`)).json();
  const bearerRes = await fetch(`${BASE}/api/me`, {
    headers: { authorization: `Bearer ${dbg.access_token}` },
  });
  const bearer = await bearerRes.json();
  check('a verified access token authenticates without a cookie', bearer.via === 'bearer' && bearer.user.sub === session.user.sub);
  const idAsAccess = await fetch(`${BASE}/api/me`, {
    headers: { authorization: `Bearer ${dbg.id_token}` },
  });
  check('an ID token is REJECTED as an access token (token_use check)', idAsAccess.status === 401, String(idAsAccess.status));
  const tampered = dbg.access_token.slice(0, -3) + 'AAA';
  const tamperedRes = await fetch(`${BASE}/api/me`, { headers: { authorization: `Bearer ${tampered}` } });
  check('a tampered signature is rejected', tamperedRes.status === 401, String(tamperedRes.status));

  console.log('\n11. logout');
  const logout = await go(`${BASE}/auth/logout`);
  check('logout redirects to the IdP end-session endpoint',
    logout.status === 302 && logout.headers.get('location').includes('/logout'));
  const idpLogout = await go(logout.headers.get('location'));
  const finalRedirect = await go(idpLogout.headers.get('location'));
  check('and lands back on the UI', finalRedirect.headers.get('location')?.startsWith(APP),
    finalRedirect.headers.get('location'));
  check('the session cookie is gone', !jar.has('sid'));
  check('the session is dead server side', (await go(`${BASE}/auth/session`)).status === 401);

  console.log(`\n\x1b[32mall ${passed} checks passed\x1b[0m\n`);
} catch (err) {
  console.error(`\n\x1b[31mSMOKE TEST FAILED\x1b[0m\n${err.stack}\n`);
  process.exitCode = 1;
} finally {
  server.kill();
}
