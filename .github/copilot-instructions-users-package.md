# AI Coding Agent Instructions for users-package

## Architecture Overview

This is a **reusable Python package for user management in Telegram bots**. The system provides three core functions:

1. **Authentication** → Check if user has access to the bot
2. **Authorization** → Verify if user has specific role
3. **Rate Limiting** → Control request frequency per user

### Key Components

- **`users/users.py`** - Main Users class: authentication, authorization, decorator-based access control
- **`users/storage.py`** - PostgreSQL client for user metadata and request logging
- **`users/ratelimiter.py`** - Request rate limiting logic (per hour/day counters)
- **`users/constants.py`** - Constants for Vault paths and user status values
- **`users/exceptions.py`** - Custom exceptions (VaultInstanceNotSet, FailedStorageConnection, etc.)
- **`tests/conftest.py`** - Pytest fixtures for Vault, PostgreSQL, test users setup
- **`tests/test_*.py`** - Comprehensive test coverage for all module functions

## Current Status & Roadmap

- Currently at **v4.1.3** (last update: 2024-12-24)
- Mature package used in production Telegram bots
- Next planned feature: **Generic token authentication support**
- Planned additions:
  - `issue_token(user_id, ttl_minutes=10) -> str` - Generate temporary access tokens
  - `validate_token(token) -> Optional[dict]` - Verify token and return user info
  - `revoke_token(user_id) -> None` - Revoke existing token (optional)
- Token storage: separate `users_tokens` table (token_hash, token_salt, token_expires_at, token_used, created_at)

## Critical Architecture Patterns

### Configuration Management
All configuration lives in **Vault** kv2 engine:
- **`configuration/users/{user_id}`** - Per-user access control and rate limits
- **`configuration/database`** - PostgreSQL connection parameters

Database credentials can come from two sources:
1. **Simple connection**: Pass `storage_connection=psycopg2.connect(...)` to Users()
2. **Vault Database Engine**: Pass `vault={'instance': <VaultClient>, 'role': 'my-role'}` for dynamic credentials

### Database Schema
Three main tables (see `tests/postgres/tables.sql`):
- **`users`** - User metadata (user_id, chat_id, status)
- **`users_requests`** - Request history (user_id, message_id, chat_id, authentication, authorization, timestamp, rate_limits)
- **`users_tokens`** - Temporary access tokens (user_id, token_hash, token_salt, token_expires_at, token_used, created_at)

### Error Handling
- **@reconnect_on_exception** decorator in storage.py - auto-reconnect on psycopg2 errors (5-second wait)
- All custom exceptions in `exceptions.py` with descriptive error messages
- Vault and storage instances validated in `__init__()` methods

### Service Boundaries
- **Users** handles auth logic only; delegates storage to Storage class, rate limiting to RateLimiter class
- **Storage** handles all database operations (register, log, query)
- **RateLimiter** calculates request counters and determines if limits are exceeded
- Classes accept either initialized instances or configuration dicts for flexibility

## Developer Workflows

### Running Tests
```bash
# Requires Vault and PostgreSQL running (docker-compose up)
pytest --verbose -s tests/
```
Tests use `@pytest.mark.order(N)` for sequential execution (critical for migration-dependent tests).

### Local Development with Docker Compose
```bash
# Start Vault and PostgreSQL
docker-compose up
# Tests auto-initialize Vault policies and database tables
```

### Building and Publishing
- **Poetry** manages dependencies (see `pyproject.toml`)
- Package published as Git tags (e.g., `v4.1.3`)
- Installed via: `users = { git = "https://github.com/obervinov/users-package.git", tag = "v4.1.3" }`

## Project-Specific Conventions

### Naming & Patterns
- Configuration keys use snake_case: `'requests_per_day'`, `'random_shift_minutes'`
- Database table names lowercase: `users`, `users_requests`
- Column naming: snake_case for database columns
- Constants UPPER_CASE: `USER_STATUS_ALLOW`, `USER_STATUS_DENY`, `USERS_VAULT_CONFIG_PATH`

### Decorators for Cross-Cutting Concerns
- `@reconnect_on_exception` (storage) - auto-reconnect on psycopg2 errors
- `@access_control()` (users) - decorator for Telegram handlers to enforce auth/authz

### User Configuration Flow
Users stored in Vault with structure:
```json
{
  "status": "allowed",
  "roles": ["admin_role", "financial_role"],
  "requests": {
    "requests_per_day": 10,
    "requests_per_hour": 1,
    "random_shift_minutes": 15
  }
}
```

### Rate Limiting Logic
- **Counters** tracked from users_requests table queries
- **Per hour**: COUNT(*) WHERE timestamp > NOW() - INTERVAL '1 hour'
- **Per day**: COUNT(*) WHERE timestamp > NOW() - INTERVAL '1 day'
- **Random shift**: Add 0-N minutes to limit expiry for load distribution

## Common Tasks

### Adding a Database Table (for tokens)
1. Update `tests/postgres/tables.sql` with new table schema
2. Existing projects using this package must handle table creation themselves
3. Storage class methods should gracefully handle missing tables (backward compatibility)
4. We need a stub in token methods if table is missing (backward compatibility)

### Adding a New Users Method
1. Define method signature in `Users` class docstring
2. Implement logic in `users/users.py`
3. Add tests in `tests/test_users_access.py` with `@pytest.mark.order(N)`
4. Update README.md with method documentation
5. Update `__init__.py` `__all__` list if adding new exceptions

### Handling a New Exception Type
1. Define exception class in `users/exceptions.py` with docstring example
2. Import in `users/__init__.py` and add to `__all__` list
3. Raise in appropriate method with descriptive message
4. Add tests for exception handling

## External Dependencies to Know
- **vault-package** (v4.0.3) - Vault API wrapper from same author
- **logger-package** (v2.0.4) - Logging wrapper from same author
- **psycopg2-binary** - PostgreSQL adapter with connection pooling
- **hvac** (test only) - Official HashiCorp Vault client for test setup

## Testing Considerations
- Vault and PostgreSQL must be running for integration tests
- Fixtures in `conftest.py` auto-setup 25+ test users with various access patterns
- Test execution order matters (use `@pytest.mark.order(N)`)
- Tests create AppRole in Vault, database engine role, and populate test data
- Cleanup happens automatically via pytest session teardown

## Token Authentication Design (Planned)

### Token Format
- Token format: `user_id.token_id` where token_id is `secrets.token_urlsafe(32)`
- Example: `"123456.a8f3kjs9dfjkl23jrlksjdf..."`
- Token length: ~45-50 characters total

### Storage Schema
Create separate `users_tokens` table:
```sql
CREATE TABLE users_tokens (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    token_hash VARCHAR(128) NOT NULL,
    token_salt VARCHAR(64) NOT NULL,
    token_expires_at TIMESTAMP NOT NULL,
    token_used BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_users_tokens_user_id ON users_tokens(user_id);
```

### Hashing Strategy
```python
import hashlib
import secrets

# Generate token
token_id = secrets.token_urlsafe(32)
salt = secrets.token_hex(32)
token_hash = hashlib.pbkdf2_hmac('sha256', token_id.encode(), salt.encode(), 100_000).hex()

# Validate token
computed_hash = hashlib.pbkdf2_hmac('sha256', provided_token_id.encode(), stored_salt.encode(), 100_000).hex()
valid = secrets.compare_digest(computed_hash, stored_hash)
```

### Method Signatures (Planned)

**Storage class methods:**
```python
def store_token(self, user_id: str, token_hash: str, token_salt: str, expires_at: datetime) -> None:
    """
    Store token data in users_tokens table.
    Marks any previous active tokens as used before inserting new one.
    """

def get_token(self, user_id: str) -> Optional[dict]:
    """
    Retrieve the most recent unused, non-expired token for user.
    Returns: dict with token_hash, token_salt, token_expires_at, token_used or None.
    """

def mark_token_used(self, user_id: str) -> None:
    """
    Mark user's active token as used (single-use enforcement).
    """
```

**Users class methods:**
```python
def issue_token(self, user_id: str, ttl_minutes: int = 10) -> str:
    """
    Generate a temporary access token for the specified user.
    
    Args:
        user_id (str): User ID to issue token for
        ttl_minutes (int): Token validity period in minutes (default 10)
    
    Returns:
        str: Token in format "user_id.token_id"
    
    Raises:
        StorageInstanceNotSet: If storage not initialized
        VaultInstanceNotSet: If vault not initialized
    """

def validate_token(self, token: str) -> Optional[dict]:
    """
    Validate a token and return user information.
    
    Args:
        token (str): Token string in format "user_id.token_id"
    
    Returns:
        dict: User information if valid {'user_id': str, 'status': str, 'roles': list}
        None: If token invalid, expired, or already used
    
    Raises:
        ValueError: If token format invalid
    """

def revoke_token(self, user_id: str) -> None:
    """
    Revoke any existing token for the specified user.
    
    Args:
        user_id (str): User ID to revoke token for
    """
```

### Token Lifecycle
1. **Issuance**: Application calls `issue_token()` → calls `storage.store_token()` with hash+salt+expiry → returns plaintext token
2. **Validation**: Application calls `validate_token()` → calls `storage.get_token()` → checks hash, expiry, used flag → returns user data or None
3. **Single-use**: After successful validation, calls `storage.mark_token_used()`
4. **Revocation**: New token issuance marks previous token as used via `storage.store_token()`

## Integration Example (pyinstabot-downloader)

### Database Bridge Pattern
- Bot calls `users.issue_token(user_id)` to generate token for user
- Frontend (WebUI) calls `users.validate_token(token)` to authenticate
- Both access same PostgreSQL `users_tokens` table
- No direct communication between bot and frontend processes
- **Note**: This is just one use case; tokens can be used for any frontend authentication (web, mobile, CLI, etc.)

### Version Coordination
- pyinstabot-downloader uses users-package via `pyproject.toml` Git tag reference
- After implementing token methods, bump users-package to v4.2.0
- Update pyinstabot-downloader's `pyproject.toml` to reference new tag
- Run `poetry update` in pyinstabot-downloader to fetch updated package

