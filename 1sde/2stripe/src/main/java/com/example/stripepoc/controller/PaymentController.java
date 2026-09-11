package com.example.stripepoc.controller;

import com.example.stripepoc.config.StripeProperties;
import com.example.stripepoc.dto.ClientConfig;
import com.example.stripepoc.dto.CreatePaymentRequest;
import com.example.stripepoc.dto.CreatePaymentResponse;
import com.example.stripepoc.dto.PaymentDto;
import com.example.stripepoc.service.PaymentService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api")
@Tag(name = "Payments", description = "Create and inspect Stripe payments.")
public class PaymentController {

    private final PaymentService service;
    private final StripeProperties props;

    public PaymentController(PaymentService service, StripeProperties props) {
        this.service = service;
        this.props = props;
    }

    @GetMapping("/config")
    @Operation(summary = "Public client config — publishable key + currency. "
            + "Safe to expose; never returns the secret key.")
    public ClientConfig config() {
        return new ClientConfig(props.getPublishableKey(), props.getCurrency());
    }

    @PostMapping("/payments/intent")
    @Operation(summary = "Create a Stripe PaymentIntent. Returns the client_secret "
            + "that the browser confirms with Stripe.js.")
    public CreatePaymentResponse createIntent(@Valid @RequestBody CreatePaymentRequest req) {
        return service.createIntent(req);
    }

    @GetMapping("/payments")
    @Operation(summary = "List recent payments (newest first).")
    public List<PaymentDto> list(@RequestParam(defaultValue = "20") int limit) {
        int safe = Math.max(1, Math.min(limit, 100));
        return service.listRecent(PageRequest.of(0, safe))
                .map(PaymentDto::from).getContent();
    }

    @GetMapping("/payments/{id}")
    @Operation(summary = "Get one payment. Also refreshes its status from Stripe.")
    public ResponseEntity<PaymentDto> get(@PathVariable UUID id) {
        return service.findById(id)
                .map(p -> service.updateStatusFromStripe(p.getStripeIntentId()).orElse(p))
                .map(PaymentDto::from)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
