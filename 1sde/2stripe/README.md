# 2stripe — local Stripe POC (Spring Boot)

A small but real Spring Boot + Stripe **test-mode** payment app you can run on
your laptop. Server creates PaymentIntents, browser confirms them with Stripe.js
Elements using Stripe's test cards. Webhook endpoint included.

- **No cloud, no production wiring.** Everything runs on `localhost:8080`.
- **Hits the actual Stripe API**, but only its test environment — you cannot
  charge real cards with a `sk_test_…` key.

## What's inside

```
2stripe/
├── pom.xml
├── README.md
├── SETUP.md                                ← configure Stripe test keys here
├── src/main/java/com/example/stripepoc/
│   ├── StripePocApplication.java
│   ├── config/   (Stripe SDK init, OpenAPI, @ConfigurationProperties)
│   ├── controller/ (PaymentController, WebhookController)
│   ├── service/  (PaymentService, StripeService — the SDK seam)
│   ├── repository/ (Spring Data JPA)
│   ├── model/    (Payment entity, PaymentStatus enum)
│   ├── dto/      (request/response records)
│   └── exception/ (PaymentException + global handler)
├── src/main/resources/
│   ├── application.yml
│   ├── application-local.yml.example       ← copy → application-local.yml
│   └── static/                             ← UI (one HTML + JS + CSS)
└── src/test/java/com/example/stripepoc/
    ├── StripePocApplicationTests.java       (context loads, no API calls)
    ├── service/PaymentServiceTest.java      (unit, Stripe mocked)
    └── integration/StripeIntegrationTest.java (hits Stripe test API)
```

## Stack

| Layer | Choice |
|---|---|
| Language / JVM | Java **21** |
| Framework | Spring Boot **3.4** (web, data-jpa, validation) |
| Stripe SDK | `com.stripe:stripe-java` 28.x |
| Database | H2 (file-mode, lives under `./data/`) |
| API docs | springdoc-openapi (Swagger UI) |
| UI | One static page + Stripe.js Elements |
| Tests | JUnit 5 + Mockito + AssertJ |

## Endpoints

| Method | Path | What |
|---|---|---|
| GET | `/` | Static checkout page |
| GET | `/api/config` | `{ publishableKey, currency }` — public bootstrap |
| POST | `/api/payments/intent` | Create a PaymentIntent → `clientSecret` |
| GET | `/api/payments` | List recent payments |
| GET | `/api/payments/{id}` | One payment (refreshes status from Stripe) |
| POST | `/api/stripe/webhook` | Stripe → server callback (signed) |
| GET | `/swagger-ui.html` | API explorer |
| GET | `/h2-console` | Browse the local DB (jdbc url shown in `application.yml`) |

## Running

```bash
# 1. configure (see SETUP.md for screenshots/links)
cp src/main/resources/application-local.yml.example \
   src/main/resources/application-local.yml
$EDITOR src/main/resources/application-local.yml    # paste sk_test_… and pk_test_…

# 2. run
./mvnw spring-boot:run        # or:  mvn spring-boot:run
# → http://localhost:8080
```

Then in the browser: enter an amount, type a Stripe test card
(`4242 4242 4242 4242`, any future expiry, any CVC), press **Pay**. The
"Recent payments" table updates and you'll see the same PaymentIntent on
your Stripe dashboard under Payments (Test mode).

## Tests

```bash
mvn test                       # context-load + unit tests (no network)
STRIPE_SECRET_KEY=sk_test_…  mvn test   # also runs StripeIntegrationTest
```

The integration test is guarded with `@EnabledIfEnvironmentVariable` so CI
without a Stripe key still passes.

## Trade-offs (on purpose)

- **No auth, no users.** Anyone with the URL can create test PaymentIntents.
  That's fine on `localhost`; not fine in production — see [`../2stripe2`](../2stripe2).
- **No saved payment methods / customers.** Each payment is one-shot.
- **No background jobs.** Status is refreshed lazily on `GET` and pushed
  by webhook when configured.
- **H2 file DB.** Swap to Postgres by changing `spring.datasource.url`.
- **CORS wide open** (default, since UI is same-origin).
