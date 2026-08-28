# Testing Patterns Skill

Reference guide for writing comprehensive, maintainable tests. Covers unit testing, integration testing, test design patterns, and common pitfalls.

## When to Use
- Writing tests for new features
- Improving test coverage
- Designing a testing strategy
- Debugging flaky tests

## Test Structure: Arrange-Act-Assert

Every test follows the same pattern:
```
1. ARRANGE: Set up test data and preconditions
2. ACT: Execute the code under test
3. ASSERT: Verify the expected outcome
```

## Unit Testing Patterns

### Pattern: One Concept Per Test
```python
# BAD: Testing multiple things
def test_user():
    user = User("john", "john@example.com")
    assert user.name == "john"
    assert user.email == "john@example.com"
    assert user.is_valid()
    user.name = ""
    assert not user.is_valid()

# GOOD: One concept per test
def test_user_creation_sets_name():
    user = User("john", "john@example.com")
    assert user.name == "john"

def test_user_with_empty_name_is_invalid():
    user = User("", "john@example.com")
    assert not user.is_valid()
```

### Pattern: Test Naming
Use descriptive names that describe the scenario:
```
test_<unit>_<scenario>_<expected>

test_calculate_total_with_discount_returns_reduced_price
test_login_with_invalid_password_returns_401
test_create_order_with_empty_cart_raises_validation_error
```

### Pattern: Test Data Builders
```python
# Instead of constructing complex objects in every test:
def make_user(**overrides):
    defaults = {
        "name": "John Doe",
        "email": "john@example.com",
        "role": "user",
        "active": True,
    }
    return User(**{**defaults, **overrides})

# Usage
def test_admin_can_delete_users():
    admin = make_user(role="admin")
    target = make_user(name="Target User")
    assert admin.can_delete(target)
```

### Pattern: Parameterized Tests
```python
import pytest

@pytest.mark.parametrize("input,expected", [
    ("hello", "HELLO"),
    ("", ""),
    ("Hello World", "HELLO WORLD"),
    ("123abc", "123ABC"),
])
def test_uppercase(input, expected):
    assert uppercase(input) == expected
```

## Integration Testing Patterns

### Pattern: Test Database with Cleanup
```python
# Use transactions for automatic cleanup
@pytest.fixture
def db_session():
    session = create_session()
    session.begin_nested()  # savepoint
    yield session
    session.rollback()      # automatic cleanup

def test_create_user_persists(db_session):
    user = User(name="test")
    db_session.add(user)
    db_session.flush()
    assert db_session.query(User).filter_by(name="test").first() is not None
```

### Pattern: API Integration Test
```python
def test_create_user_endpoint(client):
    response = client.post("/api/v1/users", json={
        "name": "John",
        "email": "john@example.com"
    })
    assert response.status_code == 201
    data = response.json()
    assert data["data"]["name"] == "John"
    assert "id" in data["data"]
```

### Pattern: External Service Mocking
```python
# Mock external APIs at the HTTP level
@responses.activate
def test_payment_processing():
    responses.add(
        responses.POST,
        "https://api.stripe.com/v1/charges",
        json={"id": "ch_123", "status": "succeeded"},
        status=200
    )
    result = process_payment(amount=1000, currency="usd")
    assert result.status == "succeeded"
```

## What to Test

### Always Test
- Happy path (normal operation)
- Validation errors (invalid inputs)
- Edge cases (empty, null, max values, boundary conditions)
- Error handling (what happens when dependencies fail)
- Security (unauthorized access, privilege escalation)

### Coverage Targets
- New code: 80%+ line coverage
- Critical paths (auth, payments, data mutation): 95%+
- Utilities and helpers: 90%+

### What NOT to Test
- Third-party library internals
- Simple getters/setters with no logic
- Framework behavior (routing, DI wiring)
- Implementation details that may change

## Common Pitfalls

### Flaky Tests
- **Cause**: Shared state between tests
  **Fix**: Each test creates its own data, cleanup in teardown
- **Cause**: Time-dependent assertions
  **Fix**: Freeze time or use time ranges
- **Cause**: Network calls in tests
  **Fix**: Mock all external HTTP calls
- **Cause**: Race conditions in async tests
  **Fix**: Proper await/sync primitives, not sleep()

### Brittle Tests
- **Cause**: Testing implementation details
  **Fix**: Test behavior/outputs, not internal methods
- **Cause**: Over-mocking
  **Fix**: Only mock at boundaries (DB, HTTP, filesystem)
- **Cause**: Asserting on exact strings/messages
  **Fix**: Assert on structure and key content, not exact text
