# 07 — Go-live checklist

Final pre-flight. **Every item must be checked** before flipping the
production switch (`sk_live_…`, real DNS, real users).

## Stripe account

- [ ] Live mode activated (business details complete, bank account
      verified, payout schedule chosen).
- [ ] Live API keys exist but are **only** in the prod secret manager.
- [ ] Restricted API keys used by the app — root secret key sealed.
- [ ] Production webhook endpoint registered, signing secret stored.
- [ ] Test mode webhook endpoint registered for staging, signing secret
      stored.
- [ ] Statement descriptor configured (what shows up on customer
      statements).
- [ ] Refund policy + dispute responses configured.
- [ ] Stripe Radar (fraud) rules reviewed; default rules are usually
      fine to start.
- [ ] Stripe Tax / VAT configured if you collect taxes.

## App

- [ ] `application.yml` profile selection works in prod (no `local`
      profile active).
- [ ] No `application-local.yml` in the built image.
- [ ] `/actuator/health` returns 200 *and* checks Stripe + DB connectivity.
- [ ] `/actuator/*` endpoints are NOT reachable from the public internet.
- [ ] Swagger UI disabled in prod, or auth-gated. Don't ship `permitAll`
      on `/swagger-ui.html` to live.
- [ ] H2 console disabled in prod (`spring.h2.console.enabled=false`).
- [ ] Database is managed Postgres, not H2.
- [ ] DB user is least-privileged (no DDL outside migrations).
- [ ] Migrations (Flyway or Liquibase) run via CI, not the app's
      `ddl-auto=update`.
- [ ] CORS is restricted to known origins.
- [ ] Rate limiting configured for `POST /api/payments/intent`
      (e.g. 10 req/min per IP at the gateway).

## Secrets

- [ ] All env-specific secrets in the secret manager (see `04`).
- [ ] No secret in CI variables visible to forked PRs.
- [ ] Rotation policy documented; calendar reminders set.
- [ ] Break-glass procedure documented for emergency rotation.

## Auth

- [ ] IdP issuer configured for prod (different from staging).
- [ ] Admin / support / billing roles assigned in the IdP, not the app.
- [ ] MFA enforced for all admin role holders.
- [ ] SSO for all engineers; no shared accounts.

## Observability

- [ ] Structured JSON logs going to the log sink.
- [ ] No secrets in logs (spot-check with a grep for `sk_`, `whsec_`).
- [ ] Metrics scraped, dashboard published.
- [ ] Five baseline alerts configured (see `06`).
- [ ] Distributed tracing working end-to-end.
- [ ] On-call rotation defined; runbook in the on-call doc.

## Network & infrastructure

- [ ] App + DB in private subnets; DB has no public IP.
- [ ] TLS cert valid, auto-renewing.
- [ ] HSTS header set on the app's responses.
- [ ] WAF in front of public endpoints with default OWASP ruleset.
- [ ] DNS TTL set low (60s) for the first 24h post-launch in case of
      rollback.

## Testing

- [ ] Full unit + integration suite green in CI.
- [ ] Staging walked through a fresh smoke test: create intent →
      confirm with test card → 3-D Secure path → webhook arrives →
      payment marked SUCCEEDED → refund → refund webhook → row updated.
- [ ] Load test at expected peak × 3 against staging.
- [ ] DR drill: restore prod DB from backup to a scratch instance and
      verify data integrity.

## Compliance

- [ ] SAQ-A on file, signed.
- [ ] Privacy policy updated to mention Stripe and what data they see.
- [ ] Cookie banner / consent if your jurisdiction needs it.
- [ ] Data subject access request process tested.

## Game day

- [ ] Run a 1-hour incident drill. Pretend the webhook secret got
      rotated incorrectly and watch alerts fire. Confirm someone gets
      paged and finds the runbook.

## Go-live moment

1. Merge the PR that switches the prod secret-manager entry from
   `sk_test_…` to `sk_live_…`.
2. Restart the app (rolling deploy).
3. Update the prod webhook endpoint in Stripe to point at live mode.
4. Make one **real** $1 payment with your own card. Refund it
   immediately. Confirm the dashboard shows both events and your DB
   agrees.
5. Open the live mode toggle on the Stripe dashboard. Watch the first
   real payment go through. Breathe.

## Post-launch (first 48h)

- [ ] Someone on-call full-time.
- [ ] Volume monitored every 15 min.
- [ ] Decline-rate baseline established for future alerting.
- [ ] Customer support trained on the new refund flow.
- [ ] DNS TTL raised back to normal once stable.

If any item is unchecked, you can absolutely still go to staging — but
you cannot go to prod. Treat this list as binary.
