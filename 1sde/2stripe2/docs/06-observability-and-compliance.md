# 06 — Observability & compliance

Payments are the canonical "I need to see exactly what happened" use
case. Build observability first, not last.

## Three pillars

### Logs

- **Structured JSON** from day one. Spring Boot + `logstash-logback-encoder`
  or `spring-boot-starter-logging` with a JSON layout. One event per line.
- **Required fields**: `ts`, `level`, `logger`, `thread`, `traceId`,
  `spanId`, `userId` (when auth'd), `paymentId`, `stripeIntentId`,
  `stripeEventId`, `requestId`.
- **Never log**: full card numbers (you don't have them, by design),
  full Stripe secret keys, OAuth tokens, password fields. Spring's
  default error pages leak query strings — disable in prod.
- **Retention**: at least 30 days hot, 1 year cold. Audit logs (see
  `03-auth-roles-permissions.md`) much longer.

### Metrics (Micrometer → Prometheus / Cloud-native)

App-level:

- `http.server.requests` (built-in) — latencies and counts per route.
- `payments.intent.created`, `payments.succeeded`, `payments.failed{reason}`.
- `stripe.api.calls{operation,outcome}` — separates "Stripe was slow"
  from "our DB was slow."
- `webhook.*` — see `05-webhooks-and-idempotency.md`.
- `jvm.memory.*`, `jvm.gc.*`, `process.cpu.usage` — basic JVM health.

Business-level (your finance team will ask):

- Gross payment volume per hour / day, by currency.
- Refund rate.
- Decline reasons distribution.

### Traces (OpenTelemetry)

Auto-instrument with the Java agent or the Spring Boot OTel starter.
Stripe SDK calls don't auto-instrument; wrap them with a manual span:

```java
Span span = tracer.spanBuilder("stripe.payment_intent.create").startSpan();
try (Scope ignored = span.makeCurrent()) {
    span.setAttribute("stripe.amount_cents", amount);
    return PaymentIntent.create(params, opts);
} finally { span.end(); }
```

Trace IDs should appear in every log line. That's how you go from
"this user reports their payment failed at 14:03" to a complete trace
in one search.

## Alerts

Start with five, add more only when they fire.

1. **5xx error rate > 1% over 5 min** — something is broken.
2. **Webhook signature failures > 0** — misconfigured secret or attack.
3. **Stripe API error rate > 5% over 5 min** — Stripe outage or your
   keys are revoked.
4. **DB connection pool > 80% used** — connection leak or slow query.
5. **Unprocessed webhook backlog > 100 events** — worker stuck.

Page on 1 and 2. Slack-only for 3-5 unless they sustain >15 min.

## Health endpoints

Add `spring-boot-starter-actuator`. Expose:

- `/actuator/health` — readiness/liveness for the load balancer.
  Customize to also report DB reachability + Stripe key presence.
- `/actuator/info` — version, git SHA, build time. Useful in incidents.
- `/actuator/metrics`, `/actuator/prometheus` — gated to internal
  network only.

## Audit logging (separate from app logs)

Every action that touches money or PII goes to an append-only audit
sink. Things that qualify:

- Issuing a refund.
- Reading another user's payment details.
- Changing a webhook secret.
- Promoting / demoting a user role.

Audit entries should be queryable by `actor`, `target`, time range, and
ideally signed (chain-of-custody) if you're in a regulated industry.

## PCI compliance — the most important property

This stack stays in **SAQ-A scope** *if and only if*:

- The browser collects card data via **Stripe.js / Elements / Checkout**
  and submits it directly to Stripe.
- Your server **never** receives, processes, or stores the PAN, CVV, or
  full track data.
- Your server **never** proxies or logs the card field's contents.
- TLS is enforced on every public URL.
- You keep an annual SAQ-A on file (Stripe provides a template).

What this means in practice for the codebase:

- The HTML form **must not** have an `<input name="card_number">`. Use
  the Stripe Element.
- Your server **must not** accept a card number in any request body.
  If you do, you're now SAQ-D-eligible and the compliance burden grows
  by an order of magnitude.

## Data handling

- **Customer email / name / address**: PII. Encrypt at rest (managed
  Postgres TDE does this by default on the major clouds). Limit who can
  query.
- **Stripe customer / payment-method IDs**: not secret, but uniquely
  identifying. Treat as PII.
- **Stripe API responses you cache**: don't cache full responses
  containing PII to public-facing CDNs.

## Region & data residency

Stripe processes payment data in regions tied to your account country.
If you have EU customers and use a US Stripe account, you may need a
Standard Contractual Clauses arrangement. Check with Stripe's
compliance docs for your country.

For *your* data (the `payments` table), keep it in a region that
matches your residency commitments to users.

## Incident readiness

Before go-live:

1. Write a one-page **payments incident runbook**:
   - How to issue an emergency refund without the app.
   - How to put the payments page in maintenance mode.
   - Who is on-call.
   - Stripe support contact.
2. Run a **game day**: pretend Stripe is down, see what your alerts and
   dashboards actually look like.
3. Confirm you can **manually replay** a failed webhook from the Stripe
   dashboard.

If you don't have these, you're not ready for prod yet.
