package com.example.stripepoc.dto;

/** What the browser needs to bootstrap Stripe.js. Never expose the secret key. */
public record ClientConfig(String publishableKey, String currency) {}
