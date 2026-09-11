package com.example.stripepoc.integration;

import com.example.stripepoc.dto.CreatePaymentRequest;
import com.example.stripepoc.dto.CreatePaymentResponse;
import com.example.stripepoc.service.PaymentService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Live integration test against Stripe's test API. Skipped automatically
 * when {@code STRIPE_SECRET_KEY} is not set, so CI without credentials still
 * passes. Set it to a {@code sk_test_…} key (never a live key) to run.
 */
@SpringBootTest(properties = {
        "spring.datasource.url=jdbc:h2:mem:itest;DB_CLOSE_DELAY=-1"
})
@EnabledIfEnvironmentVariable(named = "STRIPE_SECRET_KEY", matches = "^sk_test_.*")
class StripeIntegrationTest {

    @Autowired
    PaymentService paymentService;

    @Test
    void createIntent_hitsStripeAndReturnsClientSecret() {
        CreatePaymentResponse resp = paymentService.createIntent(
                new CreatePaymentRequest(1234, "usd", "Integration test"));

        assertThat(resp.stripeIntentId()).startsWith("pi_");
        assertThat(resp.clientSecret())
                .as("client_secret format is pi_..._secret_...")
                .matches("^pi_.+_secret_.+");
        assertThat(resp.paymentId()).isNotNull();
    }
}
