package com.example.stripepoc.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Size;

public record CreatePaymentRequest(

        @Schema(description = "Amount in the smallest currency unit (cents).",
                example = "1999", minimum = "50", maximum = "99999999")
        @Min(50) @Max(99_999_999)
        long amountCents,

        @Schema(description = "ISO-4217 currency code. Defaults to the server's "
                + "stripe.currency setting if blank.", example = "usd")
        @Size(max = 3)
        String currency,

        @Schema(description = "Free-text description shown on the Stripe dashboard.",
                example = "Test order #42")
        @Size(max = 255)
        String description
) {}
