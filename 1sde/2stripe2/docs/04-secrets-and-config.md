# 04 — Secrets and configuration

The local POC reads keys from `application-local.yml` (gitignored) or
env vars. Production must:

1. Never store secrets on disk in plain text.
2. Source secrets from a managed secret store at runtime.
3. Scope access per environment, per service.
4. Rotate on a schedule and after any suspected compromise.

## Secret inventory

These exist per environment (`staging` and `prod`):

| Key | Source | Notes |
|---|---|---|
| `stripe/secret-key` | Stripe Dashboard | `sk_test_…` in staging, `sk_live_…` in prod. Use **restricted keys**, not the root secret key. |
| `stripe/publishable-key` | Stripe Dashboard | `pk_…`. Returned to the browser via `/api/config`. Not actually secret, but kept alongside for symmetry. |
| `stripe/webhook-secret` | Stripe Dashboard → Webhooks | One per endpoint, per env. Different from the API secret. |
| `db/url` | Cloud SQL / RDS console | Includes host, port, dbname. |
| `db/username` | DB provisioning | App-specific role, not the master user. |
| `db/password` | DB provisioning | High entropy, rotated quarterly. |
| `oidc/issuer-uri` | IdP | Public URL but env-specific. |
| `oidc/client-id` | IdP | Confidential client for the app. |
| `oidc/client-secret` | IdP | Rotate at least yearly. |
| `idempotency/hmac-key` | generated | Used to derive idempotency keys deterministically from request fingerprints if you want server-side replay safety. |

## Secret stores by cloud

| Cloud | Service |
|---|---|
| AWS | Secrets Manager (preferred) or Parameter Store (cheaper) |
| GCP | Secret Manager |
| Azure | Key Vault |
| Multi | HashiCorp Vault |

All of them support: versioning, IAM-scoped reads, audit logs, automatic
rotation hooks, and integration with the major container runners.

## How the app gets them

Three patterns, pick one:

### A — Injected as env vars at boot (simplest)

The container runner (Cloud Run, ECS, Container Apps) reads the secret
and exposes it as an env var. Spring's `application.yml` already
references env vars:

```yaml
stripe:
  secret-key: ${STRIPE_SECRET_KEY:}
```

The secret never lands on disk. **Downside:** env vars are visible to
any process inside the container — fine for a single-process app, less
fine if you exec into the container.

### B — Fetched at startup via SDK

The app calls the secret-manager SDK during boot, populates a Spring
`@ConfigurationProperties` bean, and never touches env vars. Good if
your runtime doesn't have native injection.

### C — Mounted as files

The runner mounts secrets at `/var/run/secrets/...`; the app reads
them. Spring can pick these up via `spring.config.import=file:...`.
Best for Kubernetes with the CSI secrets driver.

## Rotation

- **Stripe API keys**: quarterly at minimum. Use restricted keys so you
  can mint a fresh one, deploy, then revoke the old. No downtime.
- **Webhook secrets**: when you rotate, register a *second* webhook in
  Stripe with the new secret first, deploy code that accepts either
  secret for a transition window, then drop the old endpoint.
- **DB passwords**: quarterly. Most clouds support automated rotation
  with zero downtime via the secret manager.
- **OIDC client secrets**: yearly. IdP usually supports two active
  secrets at once for rollover.

After any **suspected compromise**, rotate immediately and check the
Stripe **Logs** page for unexpected API calls in the past 30 days.

## Configuration that is NOT a secret

Things like `stripe.currency`, port numbers, log levels, feature flags —
keep these in version-controlled config (per-env values file or
parameter store). The rule: anything that, if leaked, costs money or
exposes user data → secret manager. Everything else → regular config.

## Local-dev secrets

Developers still need *some* Stripe key to test against. Best practice:

- Each developer gets their **own** `sk_test_…` from a shared Stripe
  test account (Stripe lets multiple people share one test account).
- Or: each developer runs against their own personal Stripe test
  account.
- **Never** share `sk_live_…`. It should exist in the prod secret
  manager and nowhere else.

## Common mistakes

- ❌ Committing `application-local.yml`.
- ❌ Printing secrets in startup logs ("loaded sk_test_51Ab…"). Strip
  to first 8 chars + `…` if you must log anything.
- ❌ Using one webhook secret across environments.
- ❌ Pasting the secret into a CI variable that's visible to forked PRs.
- ❌ Storing the publishable key as a secret in the browser source map.
  It's already public — embed it openly.
