# SETUP — Stripe configuration (test mode)

This document walks through every value you need to make `2stripe` actually
talk to Stripe. **All steps use Stripe test mode**, which is free and never
moves real money.

## 1. Create / sign in to Stripe

Go to https://dashboard.stripe.com/register (or log in if you already have
an account). No business details are required to use test mode.

## 2. Grab your test API keys

1. In the dashboard, make sure the toggle at the top-left says
   **"Viewing test data"** (it's a small toggle near the workspace switcher).
2. Open **Developers → API keys** (or directly: `https://dashboard.stripe.com/test/apikeys`).
3. You'll see two keys:
   - **Publishable key** — starts with `pk_test_…`. Safe to ship to the browser.
   - **Secret key** — starts with `sk_test_…`. Click **Reveal test key**. Keep it server-side only.

> **Never put a `sk_live_…` key in this project.** It would let the app
> charge real cards. This POC is for `sk_test_…` only.

## 3. Drop the keys into the app

Two options — pick one. Both work; do **not** commit either of them.

### Option A — local config file (recommended for laptop dev)

```bash
cp src/main/resources/application-local.yml.example \
   src/main/resources/application-local.yml
```

Edit it:

```yaml
stripe:
  secret-key:       sk_test_51Ab...
  publishable-key:  pk_test_51Ab...
  # webhook-secret is optional — see step 5
```

`application-local.yml` is in `.gitignore` so it never leaves your machine.

### Option B — environment variables

```bash
export STRIPE_SECRET_KEY=sk_test_51Ab...
export STRIPE_PUBLISHABLE_KEY=pk_test_51Ab...
# optional
export STRIPE_WEBHOOK_SECRET=whsec_…
```

`application.yml` already references these via `${STRIPE_SECRET_KEY:}`.

## 4. Run the app

```bash
./mvnw spring-boot:run
```

On startup, look for:

```
Stripe SDK initialised. Mode: TEST
```

If you see `Stripe is NOT configured` — the secret key didn't get picked
up. Recheck step 3.

Open http://localhost:8080. The page calls `/api/config` and you should
**not** see the orange "Stripe not configured" banner.

## 5. (Optional) Webhooks — only if you want async status updates

Stripe sends webhook events (`payment_intent.succeeded`, `…failed`,
`…requires_action`, …). On `localhost` you can't be reached from Stripe
directly; the Stripe CLI proxies for you.

```bash
# install once — https://docs.stripe.com/stripe-cli
brew install stripe/stripe-cli/stripe         # macOS
# or download a binary from the docs page on Linux/Windows

stripe login
stripe listen --forward-to localhost:8080/api/stripe/webhook
```

The first line of `stripe listen` output prints something like:

```
> Ready! Your webhook signing secret is whsec_abcdef0123…
```

Copy that `whsec_…` value into your `application-local.yml`:

```yaml
stripe:
  webhook-secret: whsec_abcdef0123…
```

Restart the app. Now when you complete a test payment in the browser,
`stripe listen` will forward the event and the server will move the
payment to `SUCCEEDED` in the database.

Without the webhook configured, the app still works — it just refreshes
status lazily when you `GET /api/payments/{id}`.

## 6. Test cards

Use these in the Stripe Elements card field:

| Card number | Outcome |
|---|---|
| `4242 4242 4242 4242` | Succeeds immediately. |
| `4000 0025 0000 3155` | Requires 3-D Secure (you'll see a modal). |
| `4000 0000 0000 9995` | Declined — insufficient funds. |
| `4000 0000 0000 0002` | Declined — generic. |
| `4000 0000 0000 0341` | Attaches OK but fails when charged. |

Any future expiry (e.g. `12 / 34`), any 3-digit CVC, any postal code.

Full list: https://docs.stripe.com/testing#cards

## 7. Verify

After a successful test payment:

- The "Recent payments" table on the page shows the new row.
- Visit https://dashboard.stripe.com/test/payments — your PaymentIntent
  is at the top of the list.
- Visit http://localhost:8080/h2-console (JDBC URL
  `jdbc:h2:file:./data/stripe-poc;AUTO_SERVER=TRUE`, user `sa`, blank
  password) and `SELECT * FROM PAYMENTS;`.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| "Stripe is NOT configured" log on startup | `stripe.secret-key` is blank — fix step 3. |
| Browser shows "Stripe not configured" banner | `/api/config` is returning an empty `publishableKey` — fix step 3. |
| `401 Unauthorized` from Stripe | Key is wrong / from a different account. |
| Webhook returns `503 webhook not configured` | `stripe.webhook-secret` is blank — fix step 5. |
| Webhook returns `400 bad signature` | Your `whsec_…` doesn't match what `stripe listen` is using. Restart `stripe listen` and grab the new value. |
| Card field is blank in the browser | The PaymentIntent failed to create — open DevTools, network tab, check `/api/payments/intent` response. |

That's it. When this runs end-to-end on your machine, you've validated
the entire client-server-Stripe round trip in test mode.
