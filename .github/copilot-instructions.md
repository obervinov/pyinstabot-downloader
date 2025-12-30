# AI Coding Agent Instructions for pyinstabot-downloader

## Architecture Overview

This is a **Telegram bot for Instagram content backup to WebDAV storage**. The system has three core data flows:

1. **User Request** (Telegram) → **Instagram Downloader** → **WebDAV Uploader** → **Cloud Storage**
2. **Configuration** sourced from **HashiCorp Vault** (kv2 engine + dynamic DB credentials)
3. **Persistence** via **PostgreSQL** with automatic migrations

### Key Components

- **`src/bot.py`** - Main orchestrator: initializes Telegram handlers, queue processor, metrics server
- **`src/modules/database.py`** - PostgreSQL client with connection pooling, migration system, and queue management
- **`src/modules/downloader.py`** - Instagram API wrapper (instagrapi) with session management and error recovery
- **`src/modules/uploader.py`** - WebDAV client for uploading media files
- **`src/modules/metrics.py`** - Prometheus metrics exporter
- **`src/modules/webui.py`** - FastAPI web interface with Telegram OAuth, dashboard, and link submission
- **`src/configs/constants.py`** - Environment variable mappings and regex patterns
- **`src/templates/`** - Jinja2 HTML templates for web UI (login, dashboard)

## Current Status & Roadmap

- Originated as a public Telegram bot; now runs as a private instance for family use. Telegram remains the lightweight front-end for input/auth.
- Next step: independent web UI that mirrors Telegram features while keeping Telegram Login for authentication/authorization.
- Web UI requirements to honor: Telegram OAuth, per-user dashboard counters (downloaded, in-queue, last-hours downloaded), paginated processed + queue views, and a form to submit new links into the queue. Reuse existing queue/processed tables and status flow.
- **Architecture boundary**: Web UI is a **read/write interface only** (displays DB state, accepts new links). All processing logic (queue processor, downloader, uploader, bot message handlers) remains in `src/bot.py`. The web app only interacts with the database via `DatabaseClient` methods like `add_message_to_queue()`, `get_user_queue()`, `get_user_processed()`, and user stats queries.

## Critical Architecture Patterns

### Configuration Management
All bot configuration lives in **Vault** (not environment files):
- **`configuration/downloader-api`** - Instagram credentials and session settings
- **`configuration/uploader-api`** - WebDAV connection parameters
- **`configuration/database`** - PostgreSQL connection details
- **`pyinstabot-downloader-database`** - Vault database engine for dynamic DB credentials

When a module initializes (e.g., `Downloader`, `Uploader`), it first attempts to read from Vault with a fallback to constructor parameters.

### Database Migrations
- Migrations are auto-discovered in `src/migrations/` with naming `NNNN_*.py`
- Each migration must define `VERSION` and `NAME` constants and an `execute(obj)` function
- The system tracks executed migrations in the `migrations` table to prevent re-running
- Failed migrations log warnings but don't halt the bot (graceful degradation in `database.py`)

### Error Handling
- **Database reconnection**: `@reconnect_on_exception` decorator attempts 5-second reconnect on psycopg2 errors
- **WebDAV reconnection**: `@exception_handler` decorator in uploader waits 60 seconds before retry
- **Instagram exceptions**: Handled in `downloader.py` with mapping to states like `download_error`
- Failed messages are stored with error status, retried via queue processor in bot main loop

### Service Boundaries
- **Downloader** only fetches; **Uploader** only stores (separation of concerns)
- **Database** handles all persistence; modules don't execute raw SQL
- **Metrics** runs in a background thread, independent of main bot logic
- **Telegram handlers** register via decorators on the bot instance

## Developer Workflows

### Running Tests
```bash
# Requires Vault and PostgreSQL running (docker-compose up)
export TG_TOKEN=test_token TG_USERID=123456
pytest --verbose -s tests/
```
Tests use fixtures in `tests/conftest.py` for Vault setup, database initialization, and teardown.

### Local Development with Docker Compose
```bash
# Start Vault, PostgreSQL, PgAdmin, and the bot
docker-compose up
# Initialize Vault with scripts/vault-init.sh
# Initialize PostgreSQL with scripts/psql-init.sh
```

### Building and Deployment
- **Poetry** manages dependencies (see `pyproject.toml`)
- **Dockerfile** uses Python 3.12.11-slim, poetry for builds, non-root user execution
- **Docker labels** capture project metadata from build args

## Project-Specific Conventions

### Naming & Patterns
- Configuration keys use kebab-case: `'source-directory'`, `'delay-requests'`
- Database table names are lowercase: `queue`, `processed`, `messages`, `users`, `accounts`, `migrations`
- Column naming: snake_case for database, camelCase avoided
- Environment variables are UPPER_CASE and prefixed (e.g., `TELEGRAM_BOT_NAME`)

### Decorators for Cross-Cutting Concerns
- `@reconnect_on_exception` (database) - auto-reconnect on psycopg2 errors
- `@exception_handler` (uploader) - retry on WebDAV connection loss
- `@exceptions_handler` (downloader) - Instagram-specific error mapping

### Message Queue & Status Flow
- Messages flow: **queue** → **processed** (with state tracking: `added`, `started`, `completed`, `download_error`, `upload_error`)
- Queue processor runs every `QUEUE_FREQUENCY` seconds (default 60s)
- Status messages sent every `STATUSES_MESSAGE_FREQUENCY` seconds (default 15s). This value relates to Telegram rate limits.

### Rate Limiting & User Roles
- Two `Users` instances: `users_rl` (rate-limited) and `users` (no limits). Two instances allows you not to use user request limits to interact with non-critical APIs.
- Roles mapped from Telegram button labels: `'Posts'` → `'posts'`, `'Account'` → `'account'`, etc.
- Allowed users tracked in database with role-based access control

## Common Tasks

### Adding a Database Table
1. Create migration in `src/migrations/NNNN_table_name.py` with `execute(obj)` function
2. Use `obj.get_connection()` and psycopg2 cursor to execute ALTER/CREATE statements
3. Track in migrations table automatically (database client handles this)

### Handling a New Instagram Exception
1. Import exception in `downloader.py`
2. Catch in try/except, map to error state (e.g., `download_error`)
3. Return status dict with `'status': 'error'` field
4. Bot processor will update message state and retry via queue

### Adding a Prometheus Metric
1. Define a `Gauge` in `Metrics.__init__()` with a descriptive name and prefix
2. Update metric values in `collect_*()` methods
3. Metrics exposed on port `METRICS_PORT` (default 8000, configurable via env var)

### Adding a Web UI Feature
1. Add route handler in `WebUI._register_routes()` method in `src/modules/webui.py`
2. Create/update Jinja2 template in `src/templates/` if needed
3. Use `DatabaseClient` methods for data access (no direct SQL)
4. Add Alpine.js `x-data` for interactive forms, htmx for partial updates
5. Web UI only reads/writes DB—no processing logic

## External Dependencies to Know
- **instagrapi** (2.1.5) - Instagram API wrapper; sessions stored locally
- **webdavclient3** (3.x) - WebDAV connection and file ops
- **psycopg2** (2.x) - PostgreSQL adapter with connection pooling
- **prometheus-client** - Metrics exposition
- **Custom packages**: `logger`, `vault`, `users`, `telegram` (from Git repos, pinned to tags)

## Testing Considerations
- Vault and PostgreSQL must be running for full integration tests
- Use pytest markers like `@pytest.mark.order(N)` for test sequencing (important for migrations)
- Fixtures auto-setup Vault policies, database tables, and cleanup after tests
- Mock mode: Downloader/Uploader can be disabled via Vault config, fallback to MagicMock objects
