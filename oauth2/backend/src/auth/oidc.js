import {
  CognitoIdentityProviderClient,
  GlobalSignOutCommand,
  GetUserCommand,
} from '@aws-sdk/client-cognito-identity-provider';
import { config, isMock, redirectUri, logoutRedirectUri, assertCognitoConfigured } from '../config.js';
import { mockRevokeUser } from '../mock/idp.js';

/**
 * The OIDC client. One implementation, two providers.
 *
 * Why the token exchange happens *here* and not in the browser:
 *   - the authorization code and the PKCE verifier never touch JavaScript that
 *     an XSS could read,
 *   - the refresh token never leaves the server,
 *   - we can use a *confidential* Cognito client (one with a secret), which a
 *     SPA fundamentally cannot do.
 *
 * The browser still talks to Cognito directly for the part that matters most:
 * the user types their password on an AWS-hosted page, not on ours.
 */

// --- endpoint metadata -------------------------------------------------------
//
// Note on discovery: Cognito publishes /.well-known/openid-configuration under
// the *issuer*, but the authorization/token endpoints it advertises there point
// at the default domain and there is no end_session_endpoint at all (Cognito's
// /logout is not standard OIDC RP-initiated logout). So for Cognito we derive
// the Hosted UI endpoints from COGNITO_DOMAIN and only trust the issuer for the
// JWKS. For the mock IdP everything is derived the same way.

export function metadata() {
  if (isMock()) {
    const issuer = `${config.baseUrl}/mock-idp`;
    return {
      issuer,
      authorizationEndpoint: `${issuer}/authorize`,
      tokenEndpoint: `${issuer}/token`,
      jwksUri: `${issuer}/.well-known/jwks.json`,
      logoutEndpoint: `${issuer}/logout`,
      clientId: 'mock-client-id',
      clientSecret: '',
    };
  }
  assertCognitoConfigured();
  const { region, userPoolId, domain, clientId, clientSecret } = config.cognito;
  const issuer = `https://cognito-idp.${region}.amazonaws.com/${userPoolId}`;
  const host = domain.startsWith('http') ? domain.replace(/\/$/, '') : `https://${domain}`;
  return {
    issuer,
    authorizationEndpoint: `${host}/oauth2/authorize`,
    tokenEndpoint: `${host}/oauth2/token`,
    jwksUri: `${issuer}/.well-known/jwks.json`,
    logoutEndpoint: `${host}/logout`,
    userInfoEndpoint: `${host}/oauth2/userInfo`,
    clientId,
    clientSecret,
  };
}

export function scopes() {
  return isMock() ? ['openid', 'email', 'profile'] : config.cognito.scopes;
}

// --- authorization request ---------------------------------------------------

/** Step 1: the URL we 302 the browser to. This is the only place AWS is "hit" by the browser. */
export function buildAuthorizeUrl({ state, nonce, codeChallenge }) {
  const m = metadata();
  const url = new URL(m.authorizationEndpoint);
  url.searchParams.set('response_type', 'code');
  url.searchParams.set('client_id', m.clientId);
  url.searchParams.set('redirect_uri', redirectUri());
  url.searchParams.set('scope', scopes().join(' '));
  url.searchParams.set('state', state);
  url.searchParams.set('nonce', nonce);
  url.searchParams.set('code_challenge', codeChallenge);
  url.searchParams.set('code_challenge_method', 'S256');
  return url.toString();
}

// --- token endpoint ----------------------------------------------------------

function tokenAuthHeaders(m) {
  const headers = { 'content-type': 'application/x-www-form-urlencoded' };
  if (m.clientSecret) {
    // Cognito expects client_secret_basic for confidential clients.
    headers.authorization =
      'Basic ' + Buffer.from(`${m.clientId}:${m.clientSecret}`).toString('base64');
  }
  return headers;
}

async function postToken(params) {
  const m = metadata();
  const res = await fetch(m.tokenEndpoint, {
    method: 'POST',
    headers: tokenAuthHeaders(m),
    body: new URLSearchParams(params),
  });
  const text = await res.text();
  let json;
  try {
    json = JSON.parse(text);
  } catch {
    throw new Error(`token endpoint returned non-JSON (${res.status}): ${text.slice(0, 200)}`);
  }
  if (!res.ok) {
    throw Object.assign(new Error(json.error_description || json.error || `token endpoint ${res.status}`), {
      status: 400,
      oauthError: json.error,
    });
  }
  return json;
}

/** Step 2: swap the one-time code (+ our PKCE verifier) for tokens. Server-to-server. */
export function exchangeCode({ code, codeVerifier }) {
  const m = metadata();
  return postToken({
    grant_type: 'authorization_code',
    client_id: m.clientId,
    code,
    redirect_uri: redirectUri(),
    code_verifier: codeVerifier,
  });
}

/** Step 3 (later): silently mint a new access token. The UI never sees this happen. */
export function refreshTokens(refreshToken) {
  const m = metadata();
  return postToken({
    grant_type: 'refresh_token',
    client_id: m.clientId,
    refresh_token: refreshToken,
  });
}

// --- logout ------------------------------------------------------------------

export function buildLogoutUrl() {
  const m = metadata();
  const url = new URL(m.logoutEndpoint);
  url.searchParams.set('client_id', m.clientId);
  url.searchParams.set('logout_uri', logoutRedirectUri());
  return url.toString();
}

// --- AWS SDK -----------------------------------------------------------------

let sdkClient = null;
function cognitoClient() {
  if (!sdkClient) {
    sdkClient = new CognitoIdentityProviderClient({ region: config.cognito.region });
  }
  return sdkClient;
}

/**
 * Kill the user's refresh tokens everywhere. The Hosted UI /logout endpoint only
 * clears the browser's IdP cookie; GlobalSignOut is what actually invalidates
 * issued refresh tokens, so a stolen one stops working.
 */
export async function globalSignOut({ accessToken, sub }) {
  if (isMock()) {
    mockRevokeUser(sub);
    return { revoked: true, via: 'mock' };
  }
  try {
    await cognitoClient().send(new GlobalSignOutCommand({ AccessToken: accessToken }));
    return { revoked: true, via: 'aws-sdk:GlobalSignOut' };
  } catch (err) {
    // An already-expired access token cannot be used to sign out; that is fine,
    // the session is being destroyed either way.
    return { revoked: false, reason: err.name ?? String(err) };
  }
}

/** Optional profile enrichment straight from the user pool, via the AWS SDK. */
export async function getUserAttributes(accessToken) {
  if (isMock()) return null;
  const out = await cognitoClient().send(new GetUserCommand({ AccessToken: accessToken }));
  return Object.fromEntries((out.UserAttributes ?? []).map((a) => [a.Name, a.Value]));
}
