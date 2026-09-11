# 02 — The sequence

This is the order to do things, written so each step *only* depends on
prior steps. Don't skip ahead — webhook config that depends on a domain
you don't own yet, for example, will leave you stuck halfway.

## Phase 0 — Pre-work (1 day)

1. **Pick a region.** Single region for v1. Pick the one closest to your
   customer base and matching Stripe account residency rules.
2. **Pick a stack** (provider + container runner + DB). See
   `01-cloud-overview.md`.
3. **Buy a domain** and confirm DNS access. You need at least
   `api.example.com` (backend) and ideally `pay.example.com` (frontend if
   split).
4. **Create two Stripe accounts** *or* configure two API key restrictions:
   one set of keys for staging (test mode), another for production
   (live mode). Keep the live key sealed until phase 6.

## Phase 1 — Identity & accounts (1 day)

1. Create a **cloud organisation / project** with billing enabled.
2. Create three accounts/projects/folders, one per env: `dev`,
   `staging`, `prod`. Bill separately if your org allows.
3. Set up **SSO** for human access (Google Workspace, Okta, Entra,
   etc.). Disable static IAM users where possible.
4. Define **roles** (admin / deployer / developer / read-only / billing).
   See `03-auth-roles-permissions.md`.

## Phase 2 — Network & data baseline (1–2 days)

1. **VPC + private subnets** per env (or your cloud's managed
   equivalent). The DB must NOT have a public IP.
2. **Managed Postgres** in each env. Smallest tier for staging.
3. **Connection limits & PITR** turned on for prod (point-in-time
   recovery, retain 7–30 days).
4. **Egress allowlist** if your provider supports it — at minimum, allow
   `api.stripe.com` and your IdP. Webhooks come *in*, so this is about
   outbound calls.
5. **Backups verified** with a tested restore on staging before you
   touch prod.

## Phase 3 — Secrets management (½ day)

1. Provision Secret Manager / Key Vault.
2. Create per-env entries:
   - `stripe/secret-key`
   - `stripe/publishable-key`
   - `stripe/webhook-secret`
   - `db/url`, `db/username`, `db/password`
   - `oidc/client-id`, `oidc/client-secret`
3. Grant the **app's runtime identity** read access to its env's
   secrets only. No human role should read prod secrets except
   break-glass.
4. Configure your app to fetch on boot (or use the provider's
   environment-injection feature). See
   `04-secrets-and-config.md`.

## Phase 4 — Build & deploy pipeline (1–2 days)

1. Containerise: `Dockerfile` building from `eclipse-temurin:21-jre`,
   running `java -jar app.jar`.
2. CI:
   - On push: `mvn verify` (unit + integration tests with
     `STRIPE_SECRET_KEY` injected from a test-mode CI secret).
   - On merge to `main`: build image, push to your registry, tag with
     git SHA.
3. CD to staging:
   - Apply infra (Terraform / Pulumi / CDK / OpenTofu).
   - Roll the new image on Cloud Run / Fargate / Container Apps.
   - Health check `/actuator/health` (add `spring-boot-starter-actuator`
     before going live).
4. CD to prod: same workflow, gated on manual approval.

## Phase 5 — Auth in front of the app (1 day)

1. Decide which endpoints are **public** (the payment flow) vs
   **protected** (admin, list-all-payments).
2. Add an OIDC integration (Spring Security + `oauth2-resource-server`).
3. Wire role checks: `@PreAuthorize("hasRole('ADMIN')")` on
   `/api/payments` (list-all) and on any future refund/cancel endpoints.
4. Public endpoints get **rate-limited** (per-IP at the load balancer or
   gateway). Stripe webhook path is auth-free but signature-verified.

## Phase 6 — Domain, TLS, and Stripe webhook hookup (½ day)

1. Point `api.example.com` at the load balancer.
2. Issue a TLS cert (provider-managed cert is easiest).
3. In the Stripe dashboard (**Developers → Webhooks**) add an endpoint
   for each environment:
   - staging → `https://api.staging.example.com/api/stripe/webhook`
   - prod    → `https://api.example.com/api/stripe/webhook`
   Select only the events you handle (`payment_intent.succeeded`,
   `.payment_failed`, `.requires_action`, plus any you add later).
4. Stripe shows a signing secret for each endpoint. Store each in its
   env's secret manager as `stripe/webhook-secret`. Restart the apps.
5. Send a test event from the dashboard → confirm 200 in your logs.

## Phase 7 — Observability (1 day)

1. Structured JSON logs to the provider's log service.
2. Metrics: payment-attempts, successes, failures by reason, webhook
   lag. Use Micrometer (already in Boot starter).
3. Traces with OpenTelemetry → your APM (Datadog, Honeycomb, Tempo).
4. Alerts on: 5xx rate, webhook signature failures, Stripe API errors
   spike, DB connection saturation.
5. Dashboards in your monitoring tool — first one to build is "payment
   funnel": intent created → confirmed → succeeded.

## Phase 8 — Pre-go-live (1 day)

See `07-go-live-checklist.md`. Includes: switching from
`sk_test_…` to `sk_live_…`, recording a refund runbook, confirming PCI
posture, dry-running an incident.

## Phase 9 — Go live

Flip prod webhook + key. Run one **real** $1 payment against your
own card, refund it. Done.

---

## Total time, conservatively

A focused engineer: **5–8 working days** to get from the local POC to a
hardened staging environment, plus a few more for prod hardening
(monitoring tuning, on-call setup, incident game day). Most of the cost
is in *not skipping* phases — every skipped step is a Sev-1 you'll
re-pay later.
