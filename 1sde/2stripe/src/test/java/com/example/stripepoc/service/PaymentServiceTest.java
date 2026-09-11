package com.example.stripepoc.service;

import com.example.stripepoc.config.StripeProperties;
import com.example.stripepoc.dto.CreatePaymentRequest;
import com.example.stripepoc.dto.CreatePaymentResponse;
import com.example.stripepoc.exception.PaymentException;
import com.example.stripepoc.model.Payment;
import com.example.stripepoc.model.PaymentStatus;
import com.example.stripepoc.repository.PaymentRepository;
import com.stripe.model.PaymentIntent;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.*;

/**
 * Unit tests for {@link PaymentService}. The Stripe SDK is mocked behind
 * {@link StripeService}, so no network is involved.
 */
class PaymentServiceTest {

    private StripeService stripe;
    private PaymentRepository repo;
    private StripeProperties props;
    private PaymentService service;

    @BeforeEach
    void setUp() {
        stripe = mock(StripeService.class);
        repo = mock(PaymentRepository.class);
        props = new StripeProperties();
        props.setSecretKey("sk_test_unit");
        props.setPublishableKey("pk_test_unit");
        props.setCurrency("usd");
        service = new PaymentService(stripe, repo, props);
    }

    @Test
    void createIntent_returnsClientSecret_andPersists() throws Exception {
        PaymentIntent fake = new PaymentIntent();
        fake.setId("pi_test_123");
        fake.setClientSecret("pi_test_123_secret_abc");
        fake.setStatus("requires_payment_method");
        when(stripe.createPaymentIntent(anyLong(), anyString(), anyString(), anyString()))
                .thenReturn(fake);
        when(repo.save(any(Payment.class))).thenAnswer(inv -> inv.getArgument(0));

        CreatePaymentResponse resp = service.createIntent(
                new CreatePaymentRequest(1999, "usd", "Test order"));

        assertThat(resp.stripeIntentId()).isEqualTo("pi_test_123");
        assertThat(resp.clientSecret()).isEqualTo("pi_test_123_secret_abc");
        assertThat(resp.publishableKey()).isEqualTo("pk_test_unit");

        ArgumentCaptor<Payment> captor = ArgumentCaptor.forClass(Payment.class);
        verify(repo).save(captor.capture());
        Payment saved = captor.getValue();
        assertThat(saved.getAmountCents()).isEqualTo(1999L);
        assertThat(saved.getCurrency()).isEqualTo("usd");
        assertThat(saved.getStatus()).isEqualTo(PaymentStatus.CREATED);
    }

    @Test
    void createIntent_rejectsWhenStripeNotConfigured() {
        props.setSecretKey("");
        assertThatThrownBy(() ->
                service.createIntent(new CreatePaymentRequest(500, "usd", "x")))
                .isInstanceOf(PaymentException.class)
                .hasMessageContaining("Stripe is not configured");
    }

    @Test
    void applyWebhookStatus_updatesExistingPayment() {
        Payment p = new Payment();
        p.setStripeIntentId("pi_test_999");
        p.setStatus(PaymentStatus.CREATED);
        when(repo.findByStripeIntentId("pi_test_999")).thenReturn(Optional.of(p));

        service.applyWebhookStatus("pi_test_999", "succeeded");

        assertThat(p.getStatus()).isEqualTo(PaymentStatus.SUCCEEDED);
    }

    @Test
    void paymentStatus_fromStripe_mappingIsCorrect() {
        assertThat(PaymentStatus.fromStripe("succeeded")).isEqualTo(PaymentStatus.SUCCEEDED);
        assertThat(PaymentStatus.fromStripe("requires_action")).isEqualTo(PaymentStatus.REQUIRES_ACTION);
        assertThat(PaymentStatus.fromStripe("processing")).isEqualTo(PaymentStatus.PROCESSING);
        assertThat(PaymentStatus.fromStripe("canceled")).isEqualTo(PaymentStatus.CANCELED);
        assertThat(PaymentStatus.fromStripe("requires_payment_method")).isEqualTo(PaymentStatus.CREATED);
        assertThat(PaymentStatus.fromStripe("weird_unknown")).isEqualTo(PaymentStatus.FAILED);
    }
}
