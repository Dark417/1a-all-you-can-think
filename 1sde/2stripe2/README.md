# 2stripe2 — taking the local POC to the cloud (docs only)

This folder is the **runbook** for promoting [`../2stripe`](../2stripe) — a
local Spring Boot + Stripe test app — into a real cloud service that can
take live payments. No code is added here. Every doc below is a checklist
of *what to set up, in what order, and why*.

> Read in order. Earlier docs justify decisions that later docs depend on.

## Docs index

| # | File | Topic |
|---|---|---|
| 01 | [`docs/01-cloud-overview.md`](docs/01-cloud-overview.md) | What "production" actually means for this app; environments; cloud provider choice; high-level architecture diagram. |
| 02 | [`docs/02-sequence.md`](docs/02-sequence.md) | The end-to-end sequence — what to provision when, and what to *not* do until later. |
| 03 | [`docs/03-auth-roles-permissions.md`](docs/03-auth-roles-permissions.md) | Authentication (OIDC), authorization (roles, scopes), API permissions, and admin access. |
| 04 | [`docs/04-secrets-and-config.md`](docs/04-secrets-and-config.md) | Where Stripe keys live, secret rotation, environment isolation. |
| 05 | [`docs/05-webhooks-and-idempotency.md`](docs/05-webhooks-and-idempotency.md) | Production-grade webhook handling, retries, idempotency, replay safety. |
| 06 | [`docs/06-observability-and-compliance.md`](docs/06-observability-and-compliance.md) | Logging, metrics, tracing, PCI scope reduction, audit trails. |
| 07 | [`docs/07-go-live-checklist.md`](docs/07-go-live-checklist.md) | Final pre-flight before flipping `sk_test_…` to `sk_live_…`. |

## TL;DR

The local POC is one process, one DB, one set of test keys. Production
adds:

- **Two environments** (staging → prod), each with its own Stripe account
  or restricted-key set, its own DB, its own secrets.
- **Auth** in front of every non-public endpoint (your customers' payments
  flow stays open; admin/list endpoints lock down behind OIDC + RBAC).
- **Secrets manager** (never env files on disk in prod).
- **Managed Postgres** instead of H2.
- **Signed webhooks**, idempotency, and a retry-safe consumer.
- **Observability**: structured logs, metrics, traces, alerting.
- **PCI scope**: never let raw card data touch your server — keep using
  Stripe.js / Elements / Checkout so you stay in SAQ-A territory.

The sequence in `docs/02-sequence.md` is the spine of all of this.
