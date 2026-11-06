# backend — the shared BFF

One Express app that all three UIs talk to. It owns the OAuth2 / OIDC flow against AWS
Cognito and exposes a small demo API behind it.

```bash
npm install
cp .env.example .env
npm run dev     # http://localhost:8080
npm run smoke   # end-to-end check of the whole flow, no browser needed
```

Default mode is `AUTH_MODE=mock`, which serves a real OIDC provider at `/mock-idp` — no AWS
account required. See [../README.md](../README.md) for the architecture and for switching
to a real user pool.

## Layout

```
src/
├── server.js               express wiring, CORS, error handling
├── config.js               all env reading happens here and nowhere else
├── auth/
│   ├── oidc.js             authorize URL, code exchange, refresh, AWS SDK calls
│   ├── tokens.js           JWKS verification (access + ID tokens)
│   ├── middleware.js       requireAuth / requireCsrf / requireGroup, transparent refresh
│   ├── store.js            login transactions + sessions (in memory)
│   └── pkce.js             RFC 7636 verifier/challenge pair
├── routes/
│   ├── auth.routes.js      /auth/login, /callback, /session, /refresh, /logout
│   └── api.routes.js       the demo notes API
├── mock/idp.js             local OIDC provider: discovery, PKCE, RS256, JWKS
└── data/notes.js           seeded in-memory demo data
```

## Reading order

If you are here to understand the flow, read in this order:

1. `routes/auth.routes.js` — the four steps, top to bottom
2. `auth/oidc.js` — what actually gets sent to Cognito
3. `auth/tokens.js` — why a token is trusted
4. `auth/middleware.js` — how that trust is applied per request

## Where AWS credentials are needed

Only in `AUTH_MODE=cognito`, and only for the AWS SDK calls in `auth/oidc.js`
(`GlobalSignOut`, `GetUser`). The OAuth2 flow itself is plain HTTPS to the Hosted UI
endpoints and needs no IAM credentials at all.
