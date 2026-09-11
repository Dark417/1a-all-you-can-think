# 01 — Cloud overview

## What changes when "local" becomes "cloud"

The local POC has a single Spring Boot process, an embedded H2 file, one
Stripe test account, and zero authentication. To run this against real
customers you must add — in roughly this order — environments, identity,
secrets management, managed data services, observability, and a deploy
pipeline.

Cloud doesn't mean "rewrite." It means **moving boundaries** from
"everything inside one JAR" to "explicit, hardened seams between services."

## Environments

At minimum, three logical environments:

| Env | Stripe mode | Purpose |
|---|---|---|
| **local** | test | Developer laptops. Shared `sk_test_…` is OK if low-trust. |
| **staging** | test | Looks like prod, hits Stripe test. Used for CI deploys and pre-release verification. |
| **production** | **live** | Real customers, real money. Different keys, different DB, separate audit trail. |

Each environment gets its own Stripe webhook signing secret, its own
secret-manager namespace, and its own DB. **Never share a database
between staging and prod, even temporarily.**

## Provider choice (any major cloud works)

Reasonable defaults:

- **AWS**: ECS Fargate (or EKS) + RDS Postgres + Secrets Manager +
  CloudFront/ALB + Cognito (or your IdP via OIDC).
- **GCP**: Cloud Run + Cloud SQL Postgres + Secret Manager + Cloud Load
  Balancing + Identity Platform.
- **Azure**: Container Apps + Azure DB for Postgres + Key Vault +
  Front Door + Entra External ID.
- **Render / Fly.io / Railway**: serverless-ish Java with managed
  Postgres and built-in secrets — good for early stages, less control.

For this app's shape (single small Spring Boot service + Postgres),
**Cloud Run / ECS Fargate / Container Apps** are all fine. Pick the one
your team already operates.

## Reference topology (illustrative)

```
                       ┌────────────────────┐
        Stripe ───────►│  WAF / Load Balancer │
                       └─────────┬──────────┘
                                 │ HTTPS
                                 ▼
                    ┌──────────────────────────┐
                    │  App container (Spring)  │   ◄── reads secrets at boot
                    │  - PaymentController     │       from Secret Manager
                    │  - WebhookController     │
                    └─────────┬────────────────┘
                              │ TLS, IAM-scoped
                              ▼
                    ┌──────────────────────────┐
                    │  Managed Postgres        │   ◄── private subnet, no public IP
                    └──────────────────────────┘
```

Browser → CDN → load balancer → app → DB. Stripe → load balancer →
app (webhook path only). Admin UIs → IdP → load balancer → app
(`/admin/**` gated by role).

## What stays the same

- The **public payment surface** is unchanged: browser confirms the
  PaymentIntent directly with Stripe.js. No card data ever transits
  your server. This is the property that keeps you in PCI **SAQ-A**.
- The **Stripe API client code** is unchanged — the SDK doesn't care
  which environment it's in.

## What must change

- H2 → managed Postgres.
- Env vars / local YAML → secret manager.
- One key set → per-environment key sets.
- No auth → IdP + roles for admin endpoints; rate limits on public ones.
- Println logs → structured JSON logs + metrics + traces.
- `mvn spring-boot:run` → containerised deploy via CI.

Each of those is covered in the next docs.
