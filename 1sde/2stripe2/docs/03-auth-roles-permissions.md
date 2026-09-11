# 03 — Auth, roles, permissions

The local POC has none of this. Production needs:

1. **Who's calling?** (authentication — identity)
2. **Are they allowed?** (authorization — RBAC + endpoint policy)
3. **Stripe-side permissions** (restricted API keys, dashboard roles)

These are three separate problems. Don't conflate them.

---

## 1. Authentication — pick an IdP, don't roll your own

Options, in roughly the order most teams should consider them:

- **Your existing IdP** (Okta, Entra ID, Google Workspace, Auth0). If
  your company has one, use it. Free integration via OIDC.
- **Cognito / Identity Platform / Entra External ID** — cloud-native,
  cheap, good for B2C.
- **Stripe-issued logins** — no. Stripe is a vendor, not an IdP.

### Wire it to Spring Boot

Add `spring-boot-starter-oauth2-resource-server`. Configure with the
issuer URL of your IdP:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/payments
          jwk-set-uri: https://idp.example.com/realms/payments/protocol/openid-connect/certs
```

The IdP issues JWTs to whatever clients you trust (your own SPA, your
admin console, partner integrations). The Spring app validates the JWT
signature and reads claims (`sub`, `email`, `roles`, `scope`).

### What about end customers paying?

Most checkout flows are **unauthenticated** — the customer is anonymous
until you have a successful payment. That's fine. The endpoints that
power checkout (`POST /api/payments/intent`) stay public; you protect
them with rate limiting and bot defences, not auth.

Authenticated checkout (for logged-in customers placing repeat orders)
is a separate flow that attaches a `customer` to the PaymentIntent —
implement once you have customer accounts.

---

## 2. Authorization — roles & route policy

Define a minimal role set up front. Add more only when there's a clear
need.

| Role | Can do |
|---|---|
| `customer` | Anonymous payment flow only. (No role required.) |
| `support` | Read payments, view individual records, search by email. |
| `support_lead` | All of `support` + issue refunds up to a cap. |
| `admin` | All read/write incl. refunds, voids, reconfigure webhooks. |
| `developer` | Read traces/logs/metrics; no DB writes; no Stripe writes. |
| `billing` | Read-only access to financial reports. |
| `auditor` | Read-only access to audit logs. |

### Map roles → endpoints

| Endpoint | Anonymous | `support` | `support_lead` | `admin` |
|---|:---:|:---:|:---:|:---:|
| `POST /api/payments/intent` | ✅ | ✅ | ✅ | ✅ |
| `GET /api/payments/{id}` | own-by-token only | by email/id | ✅ | ✅ |
| `GET /api/payments` (list) | ❌ | ✅ scoped | ✅ | ✅ |
| `POST /api/payments/{id}/refund` | ❌ | ❌ | ✅ (capped) | ✅ |
| `POST /api/stripe/webhook` | ✅ (signature-verified) | n/a | n/a | n/a |
| `/admin/**` | ❌ | ❌ | ❌ | ✅ |
| `/actuator/health` | ✅ | ✅ | ✅ | ✅ |
| `/actuator/**` (other) | ❌ | ❌ | ❌ | ✅ |

In Spring Security:

```java
http.authorizeHttpRequests(a -> a
    .requestMatchers("/", "/static/**", "/api/config",
                     "/api/payments/intent",
                     "/api/stripe/webhook",
                     "/actuator/health").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/payments/**").hasAnyRole("support", "admin")
    .requestMatchers("/api/payments/*/refund").hasAnyRole("support_lead", "admin")
    .requestMatchers("/admin/**", "/actuator/**").hasRole("admin")
    .anyRequest().authenticated()
);
```

Use `@PreAuthorize` for finer logic (e.g. "support can only see payments
matching their assigned region").

### Scopes vs roles

When the caller is a *machine* (partner integration, internal service),
prefer **scopes** in the JWT (`payments:read`, `refunds:write`). When
the caller is a *human*, prefer **roles** (which expand into scopes
inside the IdP).

---

## 3. Stripe-side permissions

Two things to lock down on the Stripe side itself:

### Restricted API keys

Don't use the full secret key in production. In **Developers → API
keys → Restricted keys**, create per-purpose keys:

- `payments-api`: allow `PaymentIntent` write, `Charge` read.
  Used by the running app.
- `webhooks` (if you split a webhook-consumer service): read-only on
  events.
- `refunds`: write `Refund`, read `Charge`. Used only by the admin
  refund flow.
- `reporting`: read-only across `Charge`, `Balance`, `Payout`. Used by
  finance jobs.

Each key gets stored in the secret manager. The app loads only the keys
it needs. **Rotate every 90 days** at minimum.

### Dashboard roles

Stripe's own user management has its own roles
(Owner / Admin / Developer / Analyst / Support / View only). Apply
least privilege there too — Engineering doesn't need Owner.

### Webhook endpoint per environment

Each environment registers its own webhook URL with its own signing
secret. Production webhooks NEVER point at a non-prod URL. This is a
common mistake when promoting environments.

---

## 4. Audit trail

Every privileged action (`refund`, `cancel`, viewing PII, changing
config) writes an audit row containing:

- timestamp (UTC, ms precision)
- actor (`sub` from JWT) and actor email
- action verb
- target id (e.g. `pi_…`, `re_…`)
- request id (correlation)
- the old + new state for state-changing actions

Store these in a separate table (or a separate database) with **append-only**
permissions. Audit logs frequently outlive the application data.

---

## 5. What NOT to do

- ❌ Don't put auth on the Stripe webhook URL. Stripe doesn't send
  bearer tokens — it sends a signature. Authenticate by verifying the
  signature instead.
- ❌ Don't share JWTs between the browser and machine clients. Different
  audiences.
- ❌ Don't store roles in your own DB *in addition to* the IdP for the
  same principal. Pick one source of truth; the IdP is the right one.
- ❌ Don't issue long-lived JWTs (>1 hour) for human users. Use refresh
  tokens.
