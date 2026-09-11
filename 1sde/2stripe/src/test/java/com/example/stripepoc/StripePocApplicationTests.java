package com.example.stripepoc;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

@SpringBootTest
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:test;DB_CLOSE_DELAY=-1",
        "stripe.secret-key=",
        "stripe.publishable-key=",
        "stripe.webhook-secret="
})
class StripePocApplicationTests {
    @Test
    void contextLoads() {
        // verifies the bean graph wires up with no Stripe creds present
    }
}
