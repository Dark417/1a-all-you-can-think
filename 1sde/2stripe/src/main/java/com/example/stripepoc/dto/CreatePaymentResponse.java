package com.example.stripepoc.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.UUID;

public record CreatePaymentResponse(

        @Schema(description = "Internal payment row id.")
        UUID paymentId,

        @Schema(description = "Stripe PaymentIntent id.", example = "pi_3PabcXyz...")
        String stripeIntentId,

        @Schema(description = "Client secret — pass to Stripe.js to confirm the payment.",
                example = "pi_3PabcXyz..._secret_...")
        String clientSecret,

        @Schema(description = "Publishable key the browser should use.")
        String publishableKey
) {}
