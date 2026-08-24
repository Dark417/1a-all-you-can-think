import crypto from 'node:crypto';

/**
 * PKCE (RFC 7636).
 *
 * Generated on the server because the server is what redeems the code. The
 * verifier is stored with the login transaction and never leaves this process,
 * so an attacker who intercepts the redirect still cannot exchange the code.
 */
export function createPkcePair() {
  const codeVerifier = crypto.randomBytes(32).toString('base64url'); // 43 chars, within RFC's 43-128
  const codeChallenge = crypto.createHash('sha256').update(codeVerifier).digest('base64url');
  return { codeVerifier, codeChallenge, codeChallengeMethod: 'S256' };
}
