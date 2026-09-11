package com.example.stripepoc.config;

import com.stripe.Stripe;
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(StripeProperties.class)
public class StripeConfig {

    private static final Logger log = LoggerFactory.getLogger(StripeConfig.class);
    private final StripeProperties props;

    public StripeConfig(StripeProperties props) {
        this.props = props;
    }

    @PostConstruct
    void initStripeClient() {
        if (!props.isConfigured()) {
            log.warn("Stripe is NOT configured — set stripe.secret-key (sk_test_...) "
                    + "before calling /api/payments/intent. See SETUP.md.");
            return;
        }
        Stripe.apiKey = props.getSecretKey();
        // Sets the User-Agent so requests are easy to spot in the Stripe dashboard.
        Stripe.setAppInfo("stripe-poc", "0.1.0", null);
        log.info("Stripe SDK initialised. Mode: {}",
                props.getSecretKey().startsWith("sk_test_") ? "TEST" : "LIVE");
    }
}
