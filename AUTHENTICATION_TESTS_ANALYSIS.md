# Authentication Tests Analysis

## Overview
The `tests/test_authentication.py` file contains several incomplete and skipped tests. This document identifies what information and setup is needed to complete them.

---

## Part 1: Existing Tests with Issues (Lines 49-166)

### Current Problems

The tests in `TestAuthenticationLogic` and `TestAuthenticationModes` have structural issues:

1. **Incorrect async/sync handling**: Tests use `asyncio.run()` to call async functions directly, but these functions have FastAPI `Depends()` parameters that cannot be resolved outside the FastAPI request context.

   Example (line 65):
   ```python
   result = asyncio.run(get_current_user_with_write_permission(user))
   ```

   The actual function signature is:
   ```python
   async def get_current_user_with_write_permission(
       current_user: Optional[dict] = Depends(get_current_user)
   ) -> Optional[dict]:
   ```

2. **Mocking challenges**: The `Depends()` mechanism requires FastAPI context, not just passing arguments directly.

### What's Needed to Fix Existing Tests

#### Option A: Test via FastAPI TestClient (Recommended)
Use the `auth_client` fixture from `conftest.py` to test through actual HTTP requests:

```python
def test_write_permission_with_token(auth_client):
    """Test write endpoint with valid write token."""
    # Mock a valid JWT token in Authorization header
    headers = {"Authorization": "Bearer <valid_token>"}
    response = auth_client.post("/entity/", headers=headers, json={...})
    assert response.status_code == 200 or 403 depending on permissions
```

**Requirements:**
- Valid JWT tokens signed with the private key
- Token must contain claims: `sub`, `permissions`, `is_admin`
- Token must be properly formatted and not expired

#### Option B: Test Functions Directly (Not Recommended)
To test the auth functions directly, you'd need to:

1. Mock the FastAPI `Depends()` resolution
2. Call the actual function body logic separately
3. This defeats the purpose of testing the integration

---

## Part 2: Skipped JWT Tests (Lines 223-242)

### Current State
Three tests are marked with `@pytest.mark.skip()` with reason: "Requires integration test environment with proper public key setup"

### What's Needed to Implement

#### Test 1: `test_valid_token_is_decoded` (Line 226)

**Purpose**: Verify that a valid JWT token is successfully decoded and returns the correct payload.

**Requirements**:
1. **Private key** - For signing the token
   - Already available from `key_pair` fixture (lines 24-47)
   - Uses EC (Elliptic Curve) with SECP256R1 curve
   - Algorithm: ES256

2. **Public key** - For validation
   - Already available from `key_pair` fixture
   - Must be in PEM format

3. **JWT token generation**:
   ```python
   from jose import jwt
   from datetime import datetime, timedelta

   # Required claims
   payload = {
       "sub": "testuser",
       "permissions": ["media_store_write"],
       "is_admin": False,
       "exp": datetime.utcnow() + timedelta(hours=1)  # Not expired
   }
   token = jwt.encode(payload, private_key, algorithm="ES256")
   ```

4. **Mock setup**:
   ```python
   with patch("src.auth.PUBLIC_KEY_PATH", str(public_key_path)):
       with patch("src.auth.AUTH_DISABLED", False):
           # Test token decoding via get_current_user()
           result = asyncio.run(get_current_user(token))
           assert result["sub"] == "testuser"
   ```

**Implementation Notes**:
- Use the `key_pair` fixture to generate keys
- Ensure token is not expired
- Test that all claims are present in returned payload
- Token should be properly base64-encoded in JWT format: `header.payload.signature`

---

#### Test 2: `test_expired_token_is_rejected` (Line 233)

**Purpose**: Verify that an expired JWT token raises HTTPException with 401 status.

**Requirements**:
1. **Generate expired token**:
   ```python
   payload = {
       "sub": "testuser",
       "permissions": ["media_store_write"],
       "is_admin": False,
       "exp": datetime.utcnow() - timedelta(hours=1)  # Already expired!
   }
   expired_token = jwt.encode(payload, private_key, algorithm="ES256")
   ```

2. **Expected behavior**:
   - `get_current_user(expired_token)` should raise `HTTPException`
   - Status code should be 401 Unauthorized
   - Error detail should mention invalid token or expiration

3. **Test assertion**:
   ```python
   with pytest.raises(HTTPException) as exc_info:
       asyncio.run(get_current_user(expired_token))

   assert exc_info.value.status_code == 401
   ```

**Implementation Notes**:
- Python-jose automatically validates `exp` claim
- Use past timestamp for expiration: `datetime.utcnow() - timedelta(hours=1)`
- The JWTError raised will be caught and converted to HTTPException in `get_current_user()`

---

#### Test 3: `test_invalid_token_format_is_rejected` (Line 240)

**Purpose**: Verify that malformed tokens are rejected with 401 status.

**Requirements**:
Test multiple invalid token formats:

1. **Not a valid JWT format**:
   ```python
   invalid_token = "not.a.valid.token.format"
   ```

2. **Invalid base64 encoding**:
   ```python
   invalid_token = "!!!invalid.base64!!!"
   ```

3. **Missing signature**:
   ```python
   invalid_token = "eyJhbGciOiJFUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0"  # Only 2 parts
   ```

4. **Signed with wrong key**:
   ```python
   # Generate another key pair
   wrong_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
   payload = {"sub": "testuser", "exp": datetime.utcnow() + timedelta(hours=1)}
   token = jwt.encode(payload, wrong_key, algorithm="ES256")
   # Try to validate with original public key - should fail
   ```

5. **Test assertion**:
   ```python
   with pytest.raises(HTTPException) as exc_info:
       asyncio.run(get_current_user(invalid_token))

   assert exc_info.value.status_code == 401
   ```

**Implementation Notes**:
- Python-jose raises `JWTError` for all malformed tokens
- All should be converted to HTTPException with 401 status
- Test multiple variations of malformed tokens

---

## Part 3: What Information is Needed

### 1. **JWT Token Structure**
The JWT tokens used by this service must have these claims:

```json
{
  "sub": "username",                    // Required: user identifier
  "permissions": ["media_store_write"], // List of permissions: media_store_read, media_store_write
  "is_admin": false,                   // Boolean: admin status
  "exp": 1234567890,                   // Unix timestamp: token expiration
  "iat": 1234567800                    // Unix timestamp: token issued at
}
```

### 2. **Key Setup**
- **Private Key**: ES256 (ECDSA with SHA-256) using SECP256R1 curve
- **Public Key**: Must be in PEM format
- The `key_pair` fixture already handles generation correctly

### 3. **Authentication Service Integration**
Since these tests are for a "Store Service" that depends on an external authentication service:
- The external auth service creates JWT tokens
- This service validates tokens using the public key
- Public key file location: `{CL_SERVER_DIR}/public_key.pem`

### 4. **Environment Setup Needed**
```python
# Mock or set these for tests:
CL_SERVER_DIR = "/tmp/test_store"
PUBLIC_KEY_PATH = "{CL_SERVER_DIR}/public_key.pem"
AUTH_DISABLED = False  # Enable auth for testing
```

### 5. **Python-Jose Configuration**
The library being used (`python-jose`):
- Algorithm: ES256 (not HS256)
- Key format: PEM (already correct)
- Default claim validation: exp, iat

---

## Part 4: Implementation Steps

### Step 1: Fix Existing Tests (Lines 49-166)
Replace direct async calls with one of these approaches:

**Option A - Use conftest.py fixtures**:
```python
def test_auth_via_http(auth_client):
    """Test authentication via HTTP request."""
    headers = {"Authorization": f"Bearer {valid_token}"}
    response = auth_client.get("/entity/", headers=headers)
    assert response.status_code in [200, 401, 403]
```

**Option B - Mock FastAPI dependencies**:
```python
def test_auth_direct():
    """Test auth logic with proper dependency injection."""
    with patch("src.auth.get_current_user") as mock_get_user:
        mock_get_user.return_value = {
            "sub": "testuser",
            "permissions": ["media_store_write"],
            "is_admin": False
        }
        # Now test get_current_user_with_write_permission
```

### Step 2: Implement JWT Tests (Lines 223-242)
```python
def test_valid_token_is_decoded(self, key_pair):
    """Valid JWT token should be decoded successfully."""
    private_pem, public_key_path = key_pair

    # Generate valid token
    from jose import jwt
    payload = {
        "sub": "testuser",
        "permissions": ["media_store_write"],
        "is_admin": False,
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    token = jwt.encode(payload, private_pem.decode(), algorithm="ES256")

    # Test decoding
    with patch("src.auth.PUBLIC_KEY_PATH", public_key_path):
        with patch("src.auth.AUTH_DISABLED", False):
            result = asyncio.run(get_current_user(token))
            assert result["sub"] == "testuser"
```

---

## Summary Table

| Test Class | Issue | Fix Required |
|-----------|-------|--------------|
| TestAuthenticationLogic | Incorrect async handling with Depends() | Use TestClient or mock dependencies |
| TestAuthenticationModes | Conditional logic makes tests incomplete | Refactor or use pytest.mark.skipif |
| TestJWTValidation | Skipped, not implemented | Generate tokens, mock public key, test validation |

---

## References
- Python-jose documentation: JWT encoding/decoding with ES256
- FastAPI security: https://fastapi.tiangolo.com/tutorial/security/
- Project's `auth.py`: Contains `get_current_user()` and related functions
- Project's `config_service.py`: Handles runtime configuration for read auth
