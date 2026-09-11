package com.example.stripepoc.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfig {

    @Bean
    public OpenAPI stripePocOpenApi() {
        return new OpenAPI().info(new Info()
                .title("Stripe POC API")
                .version("0.1.0")
                .description("Local Spring Boot + Stripe test-mode proof of concept. "
                        + "All payments hit Stripe's TEST environment when you use a "
                        + "sk_test_… secret key. See SETUP.md for configuration."));
    }
}
