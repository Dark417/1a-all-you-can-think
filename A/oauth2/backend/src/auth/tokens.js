import { createRemoteJWKSet, jwtVerify } from 'jose';
import { metadata } from './oidc.js';

/**
 * Token verification.
 *
 * Never trust a JWT because you just received it from your own token exchange -
 * verify the signature against the provider's published JWKS, and check the
 * claims. jose caches and rotates the key set for us.
 *
 * This is the same function whether the token came from a session cookie or
 * from an `Authorization: Bearer` header, and whether it was minted by the mock
 * IdP or by AWS. That is the point of making the mock a real OIDC provider.
 */

let jwks = null;
let jwksUri = null;

function keySet() {
  const m = metadata();
  if (!jwks || jwksUri !== m.jwksUri) {
    jwksUri = m.jwksUri;
    jwks = createRemoteJWKSet(new URL(m.jwksUri), {
      cooldownDuration: 30_000,
      cacheMaxAge: 10 * 60_000,
    });
  }
  return jwks;
}

/**
 * Cognito access tokens carry `client_id` rather than `aud`, and `token_use:
 * 'access'`. Checking token_use is not optional: an ID token and an access
 * token are signed by the same key, so without it an ID token would sail
 * straight through your API authorizer.
 */
export async function verifyAccessToken(token) {
  const m = metadata();
  const { payload } = await jwtVerify(token, keySet(), {
    issuer: m.issuer,
    algorithms: ['RS256'],
    clockTolerance: 5,
  });
  if (payload.token_use !== 'access') throw new Error('expected an access token');
  if (payload.client_id !== m.clientId) throw new Error('access token was issued to another client');
  return payload;
}

export async function verifyIdToken(token, { nonce } = {}) {
  const m = metadata();
  const { payload } = await jwtVerify(token, keySet(), {
    issuer: m.issuer,
    audience: m.clientId,
    algorithms: ['RS256'],
    clockTolerance: 5,
  });
  if (payload.token_use !== 'id') throw new Error('expected an ID token');
  if (nonce !== undefined && payload.nonce !== nonce) throw new Error('nonce mismatch');
  return payload;
}

/** Shape the claims we actually care about into something the UIs can render. */
export function profileFromIdToken(claims) {
  return {
    sub: claims.sub,
    username: claims['cognito:username'] ?? claims.username ?? claims.email ?? claims.sub,
    email: claims.email ?? null,
    name: claims.name ?? claims['cognito:username'] ?? null,
    groups: claims['cognito:groups'] ?? [],
  };
}
