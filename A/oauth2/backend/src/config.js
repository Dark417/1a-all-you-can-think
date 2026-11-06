import 'dotenv/config';

/**
 * Central config. Everything the auth layer needs is derived here so that the
 * rest of the code never reads process.env directly.
 *
 * AUTH_MODE=mock    -> the local mock IdP baked into this server (no AWS account needed)
 * AUTH_MODE=cognito -> a real AWS Cognito user pool
 *
 * The two modes are interchangeable on purpose: the mock IdP speaks real OIDC
 * (discovery document, PKCE, RS256 JWTs, JWKS), so not a single line of the
 * flow below is "mock-only". Flip the env var and the same code talks to AWS.
 */

const bool = (v, dflt = false) =>
  v === undefined ? dflt : ['1', 'true', 'yes', 'on'].includes(String(v).toLowerCase());

const int = (v, dflt) => (v === undefined || v === '' ? dflt : Number.parseInt(v, 10));

export const config = {
  port: int(process.env.PORT, 8080),

  /** Public URL of THIS backend. Must match the redirect URI registered with Cognito. */
  baseUrl: (process.env.APP_BASE_URL ?? 'http://localhost:8080').replace(/\/$/, ''),

  authMode: (process.env.AUTH_MODE ?? 'mock').toLowerCase(),

  /**
   * Every UI that is allowed to talk to this backend.
   *
   *  - `origin`   is used for the CORS allow-list AND to validate the ?returnTo
   *               parameter, so /auth/login can never be turned into an open redirect.
   *  - `home`     is where we drop the user after a successful login / logout.
   */
  apps: {
    react: {
      origin: process.env.REACT_APP_ORIGIN ?? 'http://localhost:5173',
      home: process.env.REACT_APP_ORIGIN ?? 'http://localhost:5173',
    },
    angular: {
      origin: process.env.ANGULAR_APP_ORIGIN ?? 'http://localhost:4200',
      home: process.env.ANGULAR_APP_ORIGIN ?? 'http://localhost:4200',
    },
    nextjs: {
      origin: process.env.NEXTJS_APP_ORIGIN ?? 'http://localhost:3000',
      home: process.env.NEXTJS_APP_ORIGIN ?? 'http://localhost:3000',
    },
  },

  cognito: {
    region: process.env.COGNITO_REGION ?? 'us-east-1',
    userPoolId: process.env.COGNITO_USER_POOL_ID ?? '',
    /** Hosted UI domain, e.g. my-app.auth.us-east-1.amazoncognito.com */
    domain: process.env.COGNITO_DOMAIN ?? '',
    clientId: process.env.COGNITO_CLIENT_ID ?? '',
    /**
     * Optional. A *confidential* client has one; a public SPA client does not.
     * Because the code exchange happens in this backend we can safely use a
     * confidential client, which is the stronger option.
     */
    clientSecret: process.env.COGNITO_CLIENT_SECRET ?? '',
    scopes: (process.env.COGNITO_SCOPES ?? 'openid email profile').split(/[ ,]+/).filter(Boolean),
  },

  session: {
    cookieName: process.env.SESSION_COOKIE_NAME ?? 'sid',
    csrfCookieName: process.env.CSRF_COOKIE_NAME ?? 'csrf_token',
    txCookieName: 'oauth_tx',
    /** Absolute session lifetime in seconds. */
    ttlSeconds: int(process.env.SESSION_TTL_SECONDS, 60 * 60 * 8),
    /**
     * Set SESSION_COOKIE_SECURE=true behind HTTPS. Locally we serve plain http
     * on localhost, where `Secure` cookies would simply be dropped.
     */
    secure: bool(process.env.SESSION_COOKIE_SECURE, false),
    /**
     * 'lax' works locally because http://localhost:5173 and http://localhost:8080
     * are the *same site* (SameSite ignores the port). If you deploy the UIs and
     * the API on different registrable domains you need 'none' + Secure.
     */
    sameSite: process.env.SESSION_COOKIE_SAMESITE ?? 'lax',
  },
};

/**
 * CORS allow-list: the three UIs, plus this backend's own origin.
 *
 * The self-origin entry matters: the mock IdP's login form posts back to this
 * same server, and browsers attach an `Origin` header to every POST navigation
 * - including same-origin ones. Without it that form submission is rejected.
 */
export const allowedOrigins = [
  ...new Set([...Object.values(config.apps).map((a) => a.origin), config.baseUrl]),
];

export const isMock = () => config.authMode === 'mock';

/** Where Cognito (or the mock IdP) sends the browser back after login. */
export const redirectUri = () => `${config.baseUrl}/auth/callback`;

/** Where the IdP sends the browser back after logout. */
export const logoutRedirectUri = () => `${config.baseUrl}/auth/logout/callback`;

export function resolveApp(name) {
  return config.apps[name] ?? null;
}

export function assertCognitoConfigured() {
  if (isMock()) return;
  const missing = ['userPoolId', 'domain', 'clientId'].filter((k) => !config.cognito[k]);
  if (missing.length) {
    throw new Error(
      `AUTH_MODE=cognito but missing COGNITO_${missing
        .map((m) => m.replace(/([A-Z])/g, '_$1').toUpperCase())
        .join(', COGNITO_')}. See .env.example.`,
    );
  }
}
