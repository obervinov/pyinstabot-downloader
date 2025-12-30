# WebUI Module

A FastAPI-based web interface for the Instagram downloader bot, providing dashboard, queue management, and link submission via Telegram OAuth.

## Overview

The WebUI module provides a **read-only presentation layer** with link submission capability:
- **Authentication**: Telegram Login Widget with HMAC-SHA256 verification
- **Dashboard**: Real-time stats (queue count, total processed, last 24h downloads)
- **Queue Management**: Paginated views of pending and completed downloads
- **Link Submission**: Form to add new Instagram URLs to the queue
- **Architecture Boundary**: WebUI only reads/writes database—all processing logic (queue processor, downloader, uploader) remains in `src/bot.py`

## Usage

```python
from modules.webui import WebUI
from modules.database import DatabaseClient
from vault import VaultClient
from configs.constants import WEBUI_PORT

# Initialize dependencies
vault = VaultClient()
database = DatabaseClient(vault=vault, db_role='pyinstabot-downloader')

# Create WebUI instance
# Configuration resolution: argument → Vault kv2 → environment → default
webui = WebUI(
    database=database,
    vault=vault,
    bot_token=None,      # Optional: arg → Vault configuration/telegram.token → raises ValueError
    session_secret=None, # Optional: arg → Vault configuration/webui.session-secret → urandom(32).hex()
    host='0.0.0.0',      # Hardcoded
    port=WEBUI_PORT,     # From constants.py (default: 8080, configurable via TELEGRAM_BOT_WEBUI_PORT env)
    templates_dir='src/templates',
    version='3.4.0'      # Application version
)

# Run in separate thread
import threading
thread = threading.Thread(target=webui.run, daemon=True)
thread.start()
```

## Configuration

### Configuration Resolution Hierarchy

All sensitive configuration follows this pattern: **argument → Vault kv2 → environment → default/error**

#### Telegram Bot Token
1. Constructor `bot_token` argument
2. Vault: `configuration/telegram` secret, key `token`
3. **Raises ValueError** if not found

#### Bot Username (for Telegram Login Widget)
1. Constructor `bot_username` argument
2. Vault: `configuration/telegram` secret, key `username`
3. Environment: `TG_USERNAME`
4. Default: `'your_bot_username'` (must be configured for widget to work)

#### Session Secret
1. Constructor `session_secret` argument
2. Vault: `configuration/webui` secret, key `session-secret`
3. Auto-generated: `os.urandom(32).hex()` (⚠️ sessions invalidated on restart)

#### Host and Port
- **Host**: Hardcoded to `'0.0.0.0'` (not configurable)
- **Port**: From `constants.WEBUI_PORT` → environment `TELEGRAM_BOT_WEBUI_PORT` → default `8080`

### Environment Variables

```bash
# Port configuration (read by constants.py)
export TELEGRAM_BOT_WEBUI_PORT=8080

# Optional: If not using Vault for bot token
export TG_TOKEN='123456:ABC-DEF'

# Optional: Bot username for Telegram Login Widget
export TG_USERNAME='your_bot_username'

# Optional: Stable session secret (recommended for production)
export WEBUI_SESSION_SECRET='your-stable-secret-key'
```

### Vault Configuration

Store secrets in HashiCorp Vault (kv2 engine):

```bash
# Telegram bot credentials
vault kv put pyinstabot-downloader/configuration/telegram \
    token='123456:ABC-DEF' \
    username='your_bot_username'

# WebUI session secret (recommended for production)
vault kv put pyinstabot-downloader/configuration/webui \
    session-secret='your-stable-secret-key'
```

## Templates

HTML templates in `src/templates/`:
- `login.html` - Telegram OAuth login page
- `dashboard.html` - Main dashboard with stats, queue, and submission form

Uses:
- **htmx** for partial page updates
- **Alpine.js** for reactive form handling
- Modern CSS with gradient backgrounds and card layouts

## Security

- **Telegram OAuth**: HMAC-SHA256 verification using bot token from Vault or constructor
- Session-based authentication
- User access control via database `users` table
- CSRF protection via session middleware
- **Token Security**: Bot token never exposed to client (server-side verification only)
- **Session Expiry**: Auth data validated within 24 hours of Telegram issuance

## API Endpoints

- `GET /` - Home (redirects to dashboard if authenticated)
- `GET /auth/telegram` - Telegram OAuth callback
- `GET /dashboard` - Main dashboard
- `GET /api/queue?page=1&limit=10` - Paginated queue
- `GET /api/processed?page=1&limit=10` - Paginated processed
- `POST /api/submit` - Submit new Instagram link
- `GET /logout` - Clear session

## Integration Example

Add to `src/bot.py` after database initialization:
from configs.constants import WEBUI_PORT

```python
from modules.webui import WebUI

# Initialize WebUI with vault and database
webui = WebUI(
    database=database,
    vault=vault,
    port=WEBUI_PORT  # Reads from constants.WEBUI_PORT
)

# Start in background thread
import threading
webui_thread = threading.Thread(target=webui.run, daemon=True)
webui_thread.start()

log.info('[bot.py]: WebUI started on port %s', WEBUI_PORT)
```

## Dependencies

Required packages (should be in `pyproject.toml`):
```toml
fastapi = "^0.110"
uvicorn = {extras = ["standard"], version = "^0.27"}
jinja2 = "^3.1"
python-multipart = "^0.0.9"
```

## Authentication Flow

1. User visits `/` → redirected to login page with Telegram Login Widget
2. User clicks widget → Telegram authenticates → redirects to `/auth/telegram?id=...&hash=...`
3. WebUI verifies HMAC-SHA256 hash using bot token
4. WebUI checks user exists in `users` table with `allowed=True`
5. If valid, user data stored in session → redirect to `/dashboard`
6. Session persists until `/logout` or server restart (if session_secret not in Vault)

**Note**: Callback method works perfectly with VPN deployments—auth flow goes through user's browser, not Telegram servers.

## Database Operations

WebUI only uses these `DatabaseClient` methods:
- `get_users(only_allowed=True)` - Check user access
- `get_user_queue(user_id, limit)` - Retrieve queue messages
- `get_user_processed(user_id, limit)` - Retrieve processed messages
- `check_message_uniqueness(post_id, user_id)` - Validate new submissions
- `add_message_to_queue(data)` - Insert new link into queue
- `_select()`, `_count()` - Low-level queries for pagination

## Production Deployment

### Recommended Setup

1. **Store secrets in Vault** (not environment variables):
    ```bash
    vault kv put pyinstabot-downloader/configuration/telegram token='...' username='...'
    vault kv put pyinstabot-downloader/configuration/webui session-secret='...'
    ```

2. **Use reverse proxy** (nginx/traefik) for HTTPS/TLS:
    ```nginx
    server {
         listen 443 ssl;
         server_name bot.yourdomain.com;
       
         location / {
              proxy_pass http://localhost:8080;
              proxy_set_header Host $host;
              proxy_set_header X-Real-IP $remote_addr;
         }
    }
    ```

3. **Update `scripts/vault-init.sh`** to include WebUI secrets:
    ```bash
    vault kv put pyinstabot-downloader/configuration/webui \
      session-secret="$(openssl rand -hex 32)"
    ```

### Future Enhancements

- [ ] Full pagination UI controls (next/prev buttons)
- [ ] WebSocket for real-time queue status updates
- [ ] Search/filter for processed messages
- [ ] Export functionality (CSV/JSON)
- [ ] Download statistics graphs
- [ ] Multi-language support
