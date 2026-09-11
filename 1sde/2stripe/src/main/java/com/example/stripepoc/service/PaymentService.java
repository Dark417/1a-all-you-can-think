package com.example.stripepoc.service;

import com.example.stripepoc.config.StripeProperties;
import com.example.stripepoc.dto.CreatePaymentRequest;
import com.example.stripepoc.dto.CreatePaymentResponse;
import com.example.stripepoc.exception.PaymentException;
import com.example.stripepoc.model.Payment;
import com.example.stripepoc.model.PaymentStatus;
import com.example.stripepoc.repository.PaymentRepository;
import com.stripe.exception.StripeException;
import com.stripe.model.PaymentIntent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Locale;
import java.util.Optional;
import java.util.UUID;

@Service
public class PaymentService {

    private static final Logger log = LoggerFactory.getLogger(PaymentService.class);

    private final StripeService stripe;
    private final PaymentRepository repo;
    private final StripeProperties props;

    public PaymentService(StripeService stripe, PaymentRepository repo, StripeProperties props) {
        this.stripe = stripe;
        this.repo = repo;
        this.props = props;
    }

    @Transactional
    public CreatePaymentResponse createIntent(CreatePaymentRequest req) {
        if (!props.isConfigured()) {
            throw new PaymentException("Stripe is not configured on the server. "
                    + "Set stripe.secret-key (sk_test_...) and restart.");
        }
        String currency = req.currency() == null || req.currency().isBlank()
                ? props.getCurrency()
                : req.currency().toLowerCase(Locale.ROOT);

        // Idempotency key: random UUID per request — guarantees that a retry of
        // *this* call returns the same PaymentIntent rather than creating a new one.
        String idempotencyKey = UUID.randomUUID().toString();

        PaymentIntent intent;
        try {
            intent = stripe.createPaymentIntent(
                    req.amountCents(),
                    currency,
                    req.description(),
                    idempotencyKey);
        } catch (StripeException e) {
            log.error("Stripe createPaymentIntent failed: {}", e.getMessage());
            throw new PaymentException("Stripe error: " + e.getMessage(), e);
        }

        Payment p = new Payment();
        p.setStripeIntentId(intent.getId());
        p.setAmountCents(req.amountCents());
        p.setCurrency(currency);
        p.setDescription(req.description());
        p.setStatus(PaymentStatus.fromStripe(intent.getStatus()));
        p = repo.save(p);

        log.info("Created Payment id={} stripeIntentId={} status={}",
                p.getId(), p.getStripeIntentId(), p.getStatus());

        return new CreatePaymentResponse(
                p.getId(),
                intent.getId(),
                intent.getClientSecret(),
                props.getPublishableKey()
        );
    }

    @Transactional
    public Optional<Payment> updateStatusFromStripe(String stripeIntentId) {
        return repo.findByStripeIntentId(stripeIntentId).map(p -> {
            try {
                PaymentIntent intent = stripe.retrievePaymentIntent(stripeIntentId);
                PaymentStatus next = PaymentStatus.fromStripe(intent.getStatus());
                if (next != p.getStatus()) {
                    log.info("Payment {} status {} -> {}", p.getId(), p.getStatus(), next);
                    p.setStatus(next);
                }
            } catch (StripeException e) {
                log.warn("Failed to refresh Stripe status for {}: {}",
                        stripeIntentId, e.getMessage());
            }
            return p;
        });
    }

    @Transactional
    public void applyWebhookStatus(String stripeIntentId, String stripeStatus) {
        repo.findByStripeIntentId(stripeIntentId).ifPresentOrElse(p -> {
            PaymentStatus next = PaymentStatus.fromStripe(stripeStatus);
            if (next != p.getStatus()) {
                log.info("Webhook: Payment {} status {} -> {}", p.getId(), p.getStatus(), next);
                p.setStatus(next);
            }
        }, () -> log.warn("Webhook for unknown PaymentIntent {} — ignored.", stripeIntentId));
    }

    @Transactional(readOnly = true)
    public Optional<Payment> findById(UUID id) {
        return repo.findById(id);
    }

    @Transactional(readOnly = true)
    public Page<Payment> listRecent(Pageable pageable) {
        return repo.findAllByOrderByCreatedAtDesc(pageable);
    }
}
