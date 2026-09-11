package com.example.stripepoc.repository;

import com.example.stripepoc.model.Payment;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;
import java.util.UUID;

@Repository
public interface PaymentRepository extends JpaRepository<Payment, UUID> {
    Optional<Payment> findByStripeIntentId(String stripeIntentId);
    Page<Payment> findAllByOrderByCreatedAtDesc(Pageable pageable);
}
