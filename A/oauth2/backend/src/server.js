import express from 'express';
import cookieParser from 'cookie-parser';
import cors from 'cors';
import { config, allowedOrigins, isMock, redirectUri, assertCognitoConfigured } from './config.js';
import { authRouter } from './routes/auth.routes.js';
import { apiRouter } from './routes/api.routes.js';
import { mockIdpRouter } from './mock/idp.js';
import { metadata } from './auth/oidc.js';

const app = express();

// Behind an ALB / CloudFront this is what makes req.protocol and Secure cookies correct.
app.set('trust proxy', 1);
app.disable('x-powered-by');

/**
 * CORS with credentials. Three separate origins share this one backend, so the
 * allow-list is explicit - `*` is not permitted alongside credentials, and you
 * would not want it here anyway.
 */
app.use(
  cors({
    origin(origin, callback) {
      // No Origin header: same-origin navigations, curl, server-to-server.
      if (!origin || allowedOrigins.includes(origin)) return callback(null, true);
      callback(new Error(`Origin ${origin} is not allowed`));
    },
    credentials: true,
    allowedHeaders: ['content-type', 'authorization', 'x-csrf-token'],
    methods: ['GET', 'POST', 'PATCH', 'DELETE', 'OPTIONS'],
  }),
);

app.use(cookieParser());
app.use(express.json({ limit: '64kb' }));

// Tiny request log - handy while you are watching the redirects fly past.
app.use((req, _res, next) => {
  if (process.env.QUIET !== '1') console.log(`${req.method} ${req.originalUrl}`);
  next();
});

if (isMock()) app.use('/mock-idp', mockIdpRouter());

app.use('/auth', authRouter());
app.use('/api', apiRouter());

app.get('/', (_req, res) => {
  res.json({
    name: 'oauth2-backend',
    authMode: config.authMode,
    docs: 'See oauth2/README.md',
    endpoints: ['/auth/config', '/auth/login?app=react', '/auth/session', '/auth/logout', '/api/notes'],
  });
});

app.use((_req, res) => res.status(404).json({ error: 'not_found' }));

// eslint-disable-next-line no-unused-vars -- express identifies error handlers by arity
app.use((err, _req, res, _next) => {
  console.error('[error]', err);
  const status = err.status ?? 500;
  res.status(status).json({ error: err.code ?? 'internal_error', message: err.message });
});

function banner() {
  const m = metadata();
  const lines = [
    '',
    `  oauth2 backend  ->  http://localhost:${config.port}`,
    `  auth mode       ->  ${config.authMode}${isMock() ? '  (no AWS account needed)' : ''}`,
    `  issuer          ->  ${m.issuer}`,
    `  redirect uri    ->  ${redirectUri()}${isMock() ? '' : '   <- register this in Cognito'}`,
    `  allowed uis     ->  ${allowedOrigins.filter((o) => o !== config.baseUrl).join('  ')}`,
  ];
  if (isMock()) lines.push('  mock users      ->  alice / Password1!  (admin),  bob / Password1!  (viewer)');
  lines.push('');
  console.log(lines.join('\n'));
}

if (!isMock()) assertCognitoConfigured();

app.listen(config.port, banner);

export { app };
