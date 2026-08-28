# API Patterns Skill

Reference guide for designing and implementing APIs. Provides patterns for REST, GraphQL, pagination, error handling, versioning, and authentication.

## When to Use
- Designing new API endpoints
- Reviewing API consistency
- Implementing pagination, filtering, or sorting
- Designing error handling strategies
- Planning API versioning

## REST Patterns

### Resource Naming
```
GET    /api/v1/users              # List users
POST   /api/v1/users              # Create user
GET    /api/v1/users/{id}         # Get user
PUT    /api/v1/users/{id}         # Update user (full)
PATCH  /api/v1/users/{id}         # Update user (partial)
DELETE /api/v1/users/{id}         # Delete user

GET    /api/v1/users/{id}/orders  # List user's orders (nested)
POST   /api/v1/users/{id}/orders  # Create order for user

# Actions (when CRUD doesn't fit)
POST   /api/v1/orders/{id}/cancel # Cancel an order (action)
POST   /api/v1/reports/generate   # Generate a report (action)
```

### Pagination
```json
// Offset-based (simple, good for small datasets)
GET /api/v1/users?page=2&limit=20

{
  "data": [...],
  "pagination": {
    "page": 2,
    "limit": 20,
    "total": 150,
    "totalPages": 8
  }
}

// Cursor-based (performant, good for large datasets)
GET /api/v1/users?cursor=eyJpZCI6MTAwfQ&limit=20

{
  "data": [...],
  "pagination": {
    "nextCursor": "eyJpZCI6MTIwfQ",
    "hasMore": true
  }
}
```

### Filtering & Sorting
```
GET /api/v1/users?status=active&role=admin        # Simple filter
GET /api/v1/users?created_after=2024-01-01         # Date filter
GET /api/v1/users?sort=created_at&order=desc       # Sorting
GET /api/v1/users?search=john                      # Full-text search
GET /api/v1/users?fields=id,name,email             # Field selection
```

### Error Response Pattern
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": [
      {
        "field": "email",
        "message": "Must be a valid email address",
        "value": "not-an-email"
      }
    ],
    "requestId": "req_abc123",
    "timestamp": "2024-01-15T10:30:00Z"
  }
}
```

### Standard Error Codes
```
VALIDATION_ERROR     - 400 - Invalid request data
UNAUTHORIZED         - 401 - Missing or invalid authentication
FORBIDDEN            - 403 - Authenticated but not permitted
NOT_FOUND            - 404 - Resource doesn't exist
CONFLICT             - 409 - State conflict (duplicate, etc.)
RATE_LIMITED         - 429 - Too many requests
INTERNAL_ERROR       - 500 - Unexpected server error
SERVICE_UNAVAILABLE  - 503 - Downstream service unavailable
```

## Authentication Patterns

### JWT Bearer Token
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...

// Token refresh flow
POST /api/v1/auth/login    → { accessToken, refreshToken }
POST /api/v1/auth/refresh  → { accessToken }  (using refreshToken)
POST /api/v1/auth/logout   → revoke refreshToken
```

### API Key
```
X-API-Key: sk_live_abc123

// Or as query parameter (less secure, for webhooks)
GET /api/v1/webhook?api_key=sk_live_abc123
```

## Versioning Strategies

### URL Path (Recommended)
```
/api/v1/users
/api/v2/users
```
Pros: Explicit, easy to route, easy to deprecate.
Cons: URL changes required for clients.

### Header-based
```
Accept: application/vnd.myapp.v2+json
```
Pros: Clean URLs. Cons: Hidden, harder to test.

## Rate Limiting Headers
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1609459200
Retry-After: 60  (on 429 responses)
```

## Idempotency
For non-idempotent operations (POST), use an idempotency key:
```
POST /api/v1/payments
Idempotency-Key: unique-client-generated-uuid
```
Server stores the key + response for 24h. Duplicate requests return the cached response.
