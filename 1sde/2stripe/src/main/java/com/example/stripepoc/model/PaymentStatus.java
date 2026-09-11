package com.example.stripepoc.model;

/** Mirrors the Stripe PaymentIntent.status values we care about, simplified. */
public enum PaymentStatus {
    CREATED,
    REQUIRES_ACTION,
    PROCESSING,
    SUCCEEDED,
    FAILED,
    CANCELED;

    public static PaymentStatus fromStripe(String stripeStatus) {
        if (stripeStatus == null) return CREATED;
        return switch (stripeStatus) {
            case "requires_payment_method", "requires_confirmation" -> CREATED;
            case "requires_action" -> REQUIRES_ACTION;
            case "processing" -> PROCESSING;
            case "succeeded" -> SUCCEEDED;
            case "canceled" -> CANCELED;
            default -> FAILED;
        };
    }
}
