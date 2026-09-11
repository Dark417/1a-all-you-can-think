package com.example.stripepoc.dto;

import com.example.stripepoc.model.Payment;
import com.example.stripepoc.model.PaymentStatus;

import java.time.Instant;
import java.util.UUID;

public record PaymentDto(
        UUID id,
        String stripeIntentId,
        long amountCents,
        String currency,
        String description,
        PaymentStatus status,
        Instant createdAt,
        Instant updatedAt
) {
    public static PaymentDto from(Payment p) {
        return new PaymentDto(
                p.getId(),
                p.getStripeIntentId(),
                p.getAmountCents(),
                p.getCurrency(),
                p.getDescription(),
                p.getStatus(),
                p.getCreatedAt(),
                p.getUpdatedAt()
        );
    }
}
