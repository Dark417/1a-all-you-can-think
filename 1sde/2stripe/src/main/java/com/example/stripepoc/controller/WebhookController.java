package com.example.stripepoc.controller;

import com.example.stripepoc.config.StripeProperties;
import com.example.stripepoc.service.PaymentService;
import com.example.stripepoc.service.StripeService;
import com.stripe.exception.SignatureVerificationException;
import com.stripe.model.Event;
import com.stripe.model.PaymentIntent;
import com.stripe.model.StripeObject;
import io.swagger.v3.oas.annotations.Hidden;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/stripe")
public class WebhookController {

    private static final Logger log = LoggerFactory.getLogger(WebhookController.class);

    private final StripeService stripe;
    private final PaymentService payments;
    private final StripeProperties props;

    public WebhookController(StripeService stripe, PaymentService payments, StripeProperties props) {
        this.stripe = stripe;
        this.payments = payments;
        this.props = props;
    }

    /**
     * Stripe webhook endpoint. Verifies the signature using the webhook secret
     * and updates the local payment row when a PaymentIntent transitions.
     *
     * <p>For local testing: run {@code stripe listen --forward-to
     * localhost:8080/api/stripe/webhook} and paste the {@code whsec_…} into
     * {@code stripe.webhook-secret}.</p>
     */
    @PostMapping("/webhook")
    @Hidden  // hidden from Swagger UI — it's invoked by Stripe, not by humans
    public ResponseEntity<String> handle(@RequestBody String payload,
                                         @RequestHeader("Stripe-Signature") String sig) {
        if (props.getWebhookSecret() == null || props.getWebhookSecret().isBlank()) {
            log.warn("Webhook called but stripe.webhook-secret is unset — refusing.");
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body("webhook not configured");
        }

        Event event;
        try {
            event = stripe.verifyWebhook(payload, sig, props.getWebhookSecret());
        } catch (SignatureVerificationException e) {
            log.warn("Webhook signature verification failed: {}", e.getMessage());
            return ResponseEntity.status(HttpStatus.BAD_REQUEST).body("bad signature");
        }

        log.info("Webhook received: type={} id={}", event.getType(), event.getId());

        StripeObject obj = event.getDataObjectDeserializer().getObject().orElse(null);
        if (obj instanceof PaymentIntent intent) {
            payments.applyWebhookStatus(intent.getId(), intent.getStatus());
        }

        // Always 200 quickly — Stripe retries on non-2xx for up to 3 days.
        return ResponseEntity.ok("ok");
    }
}
