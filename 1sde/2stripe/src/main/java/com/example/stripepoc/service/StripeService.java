package com.example.stripepoc.service;

import com.stripe.exception.StripeException;
import com.stripe.model.Event;
import com.stripe.model.PaymentIntent;
import com.stripe.net.RequestOptions;
import com.stripe.net.Webhook;
import com.stripe.param.PaymentIntentCreateParams;
import org.springframework.stereotype.Service;

/**
 * Thin wrapper over the Stripe Java SDK.
 *
 * <p>Keeps the rest of the app free of {@code com.stripe.*} imports so we can
 * mock this service in unit tests without touching the static SDK surface.</p>
 */
@Service
public class StripeService {

    /**
     * Creates a PaymentIntent on Stripe with automatic payment methods enabled.
     * An idempotency key is required to prevent duplicate charges on retry.
     */
    public PaymentIntent createPaymentIntent(long amountCents,
                                             String currency,
                                             String description,
                                             String idempotencyKey) throws StripeException {
        PaymentIntentCreateParams.Builder builder = PaymentIntentCreateParams.builder()
                .setAmount(amountCents)
                .setCurrency(currency)
                .setAutomaticPaymentMethods(
                        PaymentIntentCreateParams.AutomaticPaymentMethods.builder()
                                .setEnabled(true)
                                .build());
        if (description != null && !description.isBlank()) {
            builder.setDescription(description);
        }
        RequestOptions options = RequestOptions.builder()
                .setIdempotencyKey(idempotencyKey)
                .build();
        return PaymentIntent.create(builder.build(), options);
    }

    public PaymentIntent retrievePaymentIntent(String intentId) throws StripeException {
        return PaymentIntent.retrieve(intentId);
    }

    /** Verifies a webhook signature and returns the parsed Event. */
    public Event verifyWebhook(String payload, String sigHeader, String webhookSecret)
            throws com.stripe.exception.SignatureVerificationException {
        return Webhook.constructEvent(payload, sigHeader, webhookSecret);
    }
}
