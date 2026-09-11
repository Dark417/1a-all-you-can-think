# 05 — Webhooks & idempotency

The local POC has a webhook endpoint that verifies the signature and
updates a row. Good enough for one developer. Production needs:

1. **Fast acknowledgment** so Stripe doesn't retry unnecessarily.
2. **At-least-once processing** done safely (idempotency).
3. **Replay protection** against accidental duplicates and intentional
   replays.
4. **Backlog handling** when an event arrives out of order.
5. **Observability**: per-event tracing, age dashboards.

## The contract Stripe gives you

- Stripe retries any non-2xx response for **up to 3 days**, with
  exponential backoff. So a 5xx during a deploy is harmless; the event
  comes back.
- Events may arrive **out of order**. The status field on the
  PaymentIntent is the canonical state, not the event order.
- Events may arrive **more than once**. The `event.id` is unique;
  payload may not be (Stripe resends the same event on retry).

Source of truth: https://docs.stripe.com/webhooks.

## Production-grade handler

A clean pattern in three steps:

1. **Verify and enqueue.** The HTTP handler verifies the signature and
   writes the raw event to a `webhook_events` table (or a queue), then
   returns 200 immediately.
2. **Process asynchronously.** A worker reads events and applies them to
   domain state. This decouples webhook latency from your business logic.
3. **Mark processed.** Once applied, mark the event row processed with
   a timestamp.

### Why not just do it inline?

You already do, in the POC, and it's fine when the work is "update one
row." The moment processing grows (send email, write to ledger, call
another API), you want the work out of the HTTP request to avoid Stripe
retries triggered by your own slowness.

## Schema sketch

```sql
CREATE TABLE webhook_events (
  id              UUID PRIMARY KEY,
  stripe_event_id TEXT NOT NULL UNIQUE,    -- "evt_…"
  type            TEXT NOT NULL,           -- "payment_intent.succeeded"
  payload         JSONB NOT NULL,
  received_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  processed_at    TIMESTAMPTZ,
  attempt_count   INT NOT NULL DEFAULT 0,
  last_error      TEXT
);
CREATE INDEX ON webhook_events (processed_at) WHERE processed_at IS NULL;
```

The `UNIQUE(stripe_event_id)` constraint is the idempotency anchor. A
duplicate POST from Stripe inserts nothing — you still 200, the worker
no-ops.

## Idempotency on the *outbound* side

The POC already uses an idempotency key when creating PaymentIntents
(see `StripeService.createPaymentIntent`). In production:

- Generate the key **deterministically** from the user-visible request
  (e.g. `hmac(secret, order_id)`), not random. That way a network retry
  for the same order yields the same PaymentIntent.
- Keys are scoped per-account in Stripe; they're remembered for 24 hours.
- Never reuse a key across logically different requests — Stripe will
  return the *old* response even if the new payload differs.

For your own API endpoints (e.g. `POST /api/payments/intent`), accept
an `Idempotency-Key` header from the caller and persist
`(key, request_hash, response)` so a retry returns the same response.

## Out-of-order safety

Status transitions are not strictly ordered in webhooks. Apply a guard:

```java
private static final Map<PaymentStatus, Set<PaymentStatus>> ALLOWED = Map.of(
    CREATED,         EnumSet.of(REQUIRES_ACTION, PROCESSING, SUCCEEDED, FAILED, CANCELED),
    REQUIRES_ACTION, EnumSet.of(PROCESSING, SUCCEEDED, FAILED, CANCELED),
    PROCESSING,      EnumSet.of(SUCCEEDED, FAILED),
    SUCCEEDED,       EnumSet.of(),     // terminal
    FAILED,          EnumSet.of(),     // terminal
    CANCELED,        EnumSet.of()      // terminal
);
```

If a late `requires_action` arrives after `succeeded`, drop it. Don't
let a stale event un-succeed a payment.

## Replay safety

- Reject events older than your tolerance window (5 minutes is the
  Stripe-recommended default for the timestamp check, which the
  `Webhook.constructEvent` helper enforces).
- Reject events whose `id` you've already processed (the unique
  constraint).
- Log every signature failure with source IP — these are not normal,
  they indicate misconfiguration or attempted forgery.

## Observability

Track these as metrics:

- `webhook_received_total{type}` — counter
- `webhook_age_seconds` — histogram of `now - event.created`
- `webhook_signature_failed_total` — counter, alert on > 0
- `webhook_processed_total{type, outcome}` — counter
- `webhook_processing_latency_seconds` — histogram

Alert on:

- Signature failures > 0 in a 5-minute window.
- p95 webhook age > 30s (Stripe is retrying, or processing is stuck).
- Unprocessed backlog > 100 rows.

## Reconciliation

Even with all of the above, you need a **daily reconciliation job**:
list yesterday's PaymentIntents from the Stripe API and verify your DB
agrees. The job's existence is more important than the implementation —
it's how you catch "we missed a class of events" rather than "we missed
one event."

## Local development

Use `stripe listen --forward-to localhost:8080/api/stripe/webhook`. It
gives you a per-developer signing secret and live-streams real events
from your test account.

You can also replay specific historical events with
`stripe events resend evt_…`, useful for debugging consumer logic
without re-attempting a payment.
