"""
This module provides a FastAPI-based web UI for the Pyinstabot-Downloader bot.
It displays queue/processed messages, user statistics, and accepts new link submissions.
Authentication is handled via Telegram Login Widget.
"""
import os
import random
import hashlib
import hmac
import time
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, Request, HTTPException, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from logger import log
from src.configs.constants import ROLES_MAP
import uvicorn


class WebUI:
    """
    A FastAPI-based web interface for the Pyinstabot-Downloader bot.

    Attributes:
        app (FastAPI): FastAPI application instance.
        database (DatabaseClient): Database client for accessing queue/processed/users data.
        vault (VaultClient): Vault client for reading secrets.
        bot_token (str): Telegram bot token for verifying Telegram Login Widget authentication.
        bot_username (str): Telegram bot username for Login Widget.
        session_secret (str): Secret key for session middleware.
        token_ttl (int): Token lifetime in minutes for one-time login tokens (default 10).
        users_auth (Users): Users client without rate limits (for token auth).
        users_rl (Users): Users client with rate limits (for form submissions).
        host (str): Host address to bind the web server.
        port (int): Port to bind the web server.
        templates (Jinja2Templates): Jinja2 template renderer.

    Methods:
        verify_telegram_auth(auth_data: dict): Verify Telegram Login Widget authentication data.
        get_current_user(request: Request): Dependency to get current authenticated user from session.
        run(): Start the FastAPI web server.

    Routes:
        GET /: Home page (redirects to /dashboard if authenticated, otherwise shows login).
        GET /auth/telegram: Telegram OAuth callback handler.
        POST /auth/token: Token-based login using users-package tokens.
        GET /dashboard: User dashboard with counters and recent messages.
        GET /api/queue: Paginated queue messages for current user.
        GET /api/processed: Paginated processed messages for current user.
        POST /api/submit: Submit a new Instagram link to the queue.
        GET /logout: Clear session and redirect to home.

    Examples:
        >>> from modules.database import DatabaseClient
        >>> from vault import VaultClient
        >>> from users import Users
        >>> vault = VaultClient()
        >>> database = DatabaseClient(vault=vault, db_role='pyinstabot-downloader')
        >>> users_auth = Users(vault={'instance': vault, 'role': 'pyinstabot-users'}, rate_limits=False)
        >>> users_rl = Users(vault={'instance': vault, 'role': 'pyinstabot-users'}, rate_limits=True)
        >>> webui = WebUI(
        ...     database=database,
        ...     vault=vault,
        ...     users={'auth': users_auth, 'rate_limited': users_rl},
        ...     port=8080
        ... )
        >>> # Run in separate thread or process
        >>> import threading
        >>> thread = threading.Thread(target=webui.run, daemon=True)
        >>> thread.start()
    """

    def __init__(self, database: object, vault: object, users: dict, **kwargs):
        """
        Initialize the WebUI instance.

        Args:
            database (DatabaseClient): Database client instance for accessing data (required).
            vault (object): Vault client instance for accessing secrets (required).
            users (dict): Users clients for auth and rate limiting (required).
                Expected keys:
                    'auth' (Users): Users client without rate limits for token authentication.
                    'rate_limited' (Users): Users client with rate limits for form submissions.
            **kwargs: Optional configuration:
                bot_token (str): Telegram bot token (fallback to Vault configuration/telegram.token)
                bot_username (str): Telegram bot username for Login Widget (fallback to Vault)
                session_secret (str): Secret key for session cookies (fallback to Vault or auto-generate)
                host (str): Host to bind the web server (default '0.0.0.0')
                port (int): Port to bind the web server (default from constants)
                templates_dir (str): Directory containing Jinja2 templates (default 'src/templates')
                version (str): Application version string (default '0.0.0')
        """
        self.database = database
        self.vault = vault

        # Extract kwargs with defaults
        bot_token = kwargs.get('bot_token')
        bot_username = kwargs.get('bot_username')
        session_secret = kwargs.get('session_secret')
        host = kwargs.get('host', '0.0.0.0')
        port = kwargs.get('port')
        templates_dir = kwargs.get('templates_dir', 'src/templates')
        version = kwargs.get('version', '0.0.0')
        token_ttl = kwargs.get('token_ttl')

        # Extract Users clients from required users dict
        self.users_auth = users.get('auth') if users else None
        self.users_rl = users.get('rate_limited') if users else None

        # Load secrets from Vault
        telegram_secret = self.vault.kv2engine.read_secret(path='configuration/telegram')
        webui_secret = self.vault.kv2engine.read_secret(path='configuration/webui')

        # Extract configuration values from arguments or Vault
        if bot_token:
            self.bot_token = bot_token
        else:
            self.bot_token = telegram_secret.get('token')

        if bot_username:
            self.bot_username = bot_username
        else:
            self.bot_username = telegram_secret.get('username')

        if session_secret:
            self.session_secret = session_secret
        # Fallback to Vault or auto-generate
        else:
            self.session_secret = webui_secret.get('session-secret', os.urandom(32).hex())

        if token_ttl:
            self.token_ttl = token_ttl
        # Fallback to Vault or default 10 minutes
        else:
            self.token_ttl = int(webui_secret.get('token-ttl', 10))

        # Host and port configuration
        self.host = host
        self.port = port

        # Validate required attributes
        missing = []
        if not self.database:
            missing.append('database')
        if not self.vault:
            missing.append('vault')
        if not self.users_auth:
            missing.append("users['auth']")
        if not self.users_rl:
            missing.append("users['rate_limited']")
        if not self.bot_token:
            missing.append('bot_token (via argument or Vault configuration/telegram.token)')
        if not self.bot_username:
            missing.append('bot_username (via argument or Vault configuration/telegram.username)')
        if not self.session_secret:
            missing.append('session_secret (via argument or Vault configuration/webui.session-secret)')

        if missing:
            raise ValueError(f"Missing required WebUI configuration: {', '.join(missing)}")

        # Initialize FastAPI app
        self.app = FastAPI(title="Instagram Downloader WebUI", version=version)
        self.app.add_middleware(SessionMiddleware, secret_key=self.session_secret)

        # Mount static files
        self.app.mount("/static", StaticFiles(directory="src/static"), name="static")

        # Setup templates
        self.templates = Jinja2Templates(directory=templates_dir)

        # Register routes
        self._register_routes()

        log.info('[WebUI]: Initialized on %s:%s', self.host, self.port)

    def verify_telegram_auth(self, auth_data: dict) -> bool:
        """
        Verify Telegram Login Widget authentication data.

        Args:
            auth_data (dict): Authentication data from Telegram Login Widget.
                Expected keys: id, first_name, username, photo_url, auth_date, hash

        Returns:
            bool: True if authentication is valid, False otherwise.

        Reference:
            https://core.telegram.org/widgets/login#checking-authorization
        """
        try:
            check_hash = auth_data.pop('hash', None)
            if not check_hash:
                return False

            # Create data-check-string
            data_check_arr = [f"{k}={v}" for k, v in sorted(auth_data.items())]
            data_check_string = '\n'.join(data_check_arr)

            # Generate secret key from bot token
            secret_key = hashlib.sha256(self.bot_token.encode()).digest()

            # Calculate hash
            computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

            # Verify hash matches and auth_date is recent (within 24 hours)
            auth_date = int(auth_data.get('auth_date', 0))
            if computed_hash == check_hash and (time.time() - auth_date) < 86400:
                return True

            return False
        except Exception as error:
            log.error('[WebUI]: Error verifying Telegram auth: %s', str(error))
            return False

    def get_current_user(self, request: Request) -> Optional[dict]:
        """
        FastAPI dependency to get current authenticated user from session.

        Args:
            request (Request): FastAPI request object.

        Returns:
            dict: User data from session if authenticated, None otherwise.

        Raises:
            HTTPException: 401 if user is not authenticated.
        """
        user = request.session.get('user')
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return user

    def _register_routes(self):
        """Register all FastAPI routes for the web UI."""

        @self.app.get("/", response_class=HTMLResponse)
        async def home(request: Request):
            """Home page - redirects to dashboard if authenticated, otherwise shows login."""
            user = request.session.get('user')
            if user:
                return RedirectResponse(url='/dashboard')
            return self.templates.TemplateResponse(
                "login.html",
                {"request": request, "bot_username": self.bot_username, "token_enabled": bool(self.users_auth)}
            )

        @self.app.get("/auth/telegram")
        async def telegram_auth(request: Request):
            """
            Telegram OAuth callback handler.
            Verifies authentication data and creates session.
            """
            auth_data = dict(request.query_params)

            if not self.verify_telegram_auth(auth_data):
                log.warning('[WebUI]: Invalid Telegram authentication attempt from %s', request.client.host)
                raise HTTPException(status_code=401, detail="Invalid authentication")

            user_id = auth_data.get('id')

            # Check if user is allowed
            allowed_users = self.database.get_users(only_allowed=True)
            if not any(str(user.get('user_id')) == str(user_id) for user in allowed_users):
                log.warning('[WebUI]: Access denied for user %s', user_id)
                raise HTTPException(status_code=403, detail="Access denied")

            # Store user in session
            request.session['user'] = {
                'id': user_id,
                'first_name': auth_data.get('first_name', ''),
                'username': auth_data.get('username', ''),
                'photo_url': auth_data.get('photo_url', '')
            }

            log.info('[WebUI]: User %s authenticated successfully', user_id)
            return RedirectResponse(url='/dashboard')

        @self.app.post("/auth/token")
        async def token_auth(request: Request, token: str = Form(...)):
            """
            Token-based authentication handler using Users package tokens.
            """
            if not self.users_auth:
                log.error('[WebUI]: Token authentication requested but Users client is not configured')
                raise HTTPException(status_code=503, detail="Token authentication not configured")

            token_value = token.strip()
            try:
                token_data = self.users_auth.validate_token(token_value)
            except Exception as error:
                log.warning('[WebUI]: Token validation failed: %s', str(error))
                raise HTTPException(status_code=401, detail="Invalid or expired token") from error

            if not token_data:
                raise HTTPException(status_code=401, detail="Invalid or expired token")

            user_id = str(token_data.get('user_id') or token_value.split('.', maxsplit=1)[0])

            allowed_users = self.database.get_users(only_allowed=True) or []
            if not any(str(user.get('user_id')) == user_id for user in allowed_users):
                log.warning('[WebUI]: Access denied for user %s via token', user_id)
                raise HTTPException(status_code=403, detail="Access denied")

            # Generate random DiceBear avatar if photo_url is missing
            username = token_data.get('username', str(user_id))
            photo_url = token_data.get('photo_url', '')
            if not photo_url:
                styles = ['adventurer', 'avataaars', 'lorelei', 'micah', 'notionists', 'pixel-art']
                style = random.choice(styles)
                photo_url = f"https://api.dicebear.com/7.x/{style}/svg?seed={username}"

            request.session['user'] = {
                'id': user_id,
                'first_name': token_data.get('username', ''),
                'username': username,
                'photo_url': photo_url
            }

            log.info('[WebUI]: User %s authenticated successfully via token', user_id)
            return RedirectResponse(url='/dashboard', status_code=303)

        @self.app.get("/dashboard", response_class=HTMLResponse)
        async def dashboard(request: Request, user: dict = Depends(self.get_current_user)):
            """
            User dashboard showing counters and recent messages.
            """
            user_id = user['id']

            # Get statistics
            queue_data = self.database.get_user_queue(user_id=str(user_id), limit=5)
            processed_data = self.database.get_user_processed(user_id=str(user_id), limit=5)

            # Calculate last 24 hours downloads
            now = datetime.now()
            last_24h = now - timedelta(hours=24)
            # Query processed messages from last 24 hours
            recent_processed = self.database._select(
                table_name='processed',
                columns=('COUNT(*)',),
                condition=f"user_id = '{user_id}' AND timestamp >= '{last_24h.strftime('%Y-%m-%d %H:%M:%S')}'"
            )
            last_24h_count = recent_processed[0][0] if recent_processed else 0

            context = {
                "request": request,
                "user": user,
                "queue_count": queue_data['counter'],
                "processed_count": processed_data['counter'],
                "last_24h_count": last_24h_count,
                "recent_queue": queue_data['messages'],
                "recent_processed": processed_data['messages']
            }

            return self.templates.TemplateResponse("dashboard.html", context)

        @self.app.get("/api/queue")
        async def get_queue(
            request: Request,
            page: int = 1,
            limit: int = 10,
            user: dict = Depends(self.get_current_user)
        ):
            """
            Get paginated queue messages for current user.

            Query params:
                page (int): Page number (default: 1)
                limit (int): Items per page (default: 10)
            """
            user_id = str(user['id'])
            offset = (page - 1) * limit

            messages = self.database._select(
                table_name='queue',
                columns=('post_id', 'post_url', 'post_owner', 'scheduled_time', 'state', 'download_status', 'upload_status'),
                condition=f"user_id = '{user_id}'",
                order_by='scheduled_time ASC',
                limit=limit,
                offset=offset
            )

            total = self.database._count(table_name='queue', condition=f"user_id = '{user_id}'")

            result = []
            if messages:
                for msg in messages:
                    result.append({
                        'post_id': msg[0],
                        'post_url': msg[1],
                        'post_owner': msg[2],
                        'scheduled_time': msg[3].isoformat() if msg[3] else None,
                        'state': msg[4],
                        'download_status': msg[5],
                        'upload_status': msg[6]
                    })

            return JSONResponse({
                'total': total,
                'page': page,
                'limit': limit,
                'messages': result
            })

        @self.app.get("/api/processed")
        async def get_processed(
            request: Request,
            page: int = 1,
            limit: int = 10,
            user: dict = Depends(self.get_current_user)
        ):
            """
            Get paginated processed messages for current user.

            Query params:
                page (int): Page number (default: 1)
                limit (int): Items per page (default: 10)
            """
            user_id = str(user['id'])
            offset = (page - 1) * limit

            messages = self.database._select(
                table_name='processed',
                columns=('post_id', 'post_url', 'post_owner', 'timestamp', 'state', 'download_status', 'upload_status'),
                condition=f"user_id = '{user_id}'",
                order_by='timestamp DESC',
                limit=limit,
                offset=offset
            )

            total = self.database._count(table_name='processed', condition=f"user_id = '{user_id}'")

            result = []
            if messages:
                for msg in messages:
                    result.append({
                        'post_id': msg[0],
                        'post_url': msg[1],
                        'post_owner': msg[2],
                        'timestamp': msg[3].isoformat() if msg[3] else None,
                        'state': msg[4],
                        'download_status': msg[5],
                        'upload_status': msg[6]
                    })

            return JSONResponse({
                'total': total,
                'page': page,
                'limit': limit,
                'messages': result
            })

        @self.app.post("/api/submit")
        async def submit_link(
            request: Request,
            url: str = Form(...),
            user: dict = Depends(self.get_current_user)
        ):
            """
            Submit Instagram link(s) to the queue.
            Supports single link or multiple links separated by newlines or commas.

            Form data:
                url (str): Instagram post/profile URL(s)
            """
            import re
            from configs.constants import REGEX_SPECIFIC_LINK, REGEX_PROFILE_LINK

            user_id = str(user['id'])

            # Parse multiple links (newline or comma-separated)
            raw_urls = url.strip()
            # Split by newlines first, then by commas
            urls = []
            for line in raw_urls.split('\n'):
                for part in line.split(','):
                    cleaned = part.strip()
                    if cleaned:
                        urls.append(cleaned)

            if not urls:
                raise HTTPException(status_code=400, detail="No URLs provided")

            results = {'success': [], 'errors': []}

            # Process each URL with per-link authorization and rate limiting
            for idx, single_url in enumerate(urls):
                try:
                    # Remove query parameters
                    clean_url = single_url.split('?')[0]

                    # Validate URL format and determine link type
                    if re.match(REGEX_SPECIFIC_LINK, single_url):
                        link_type = 'post'
                        required_role = ROLES_MAP['Posts']  # 'posts'
                        post_id = clean_url.split('/')[4]
                        # Validate post_id (Instagram shortcodes are 11 characters)
                        if len(post_id) != 11 or not re.match(r'^[a-zA-Z0-9_-]+$', post_id):
                            results['errors'].append({'url': single_url, 'error': 'Invalid post shortcode format'})
                            continue
                    elif re.match(REGEX_PROFILE_LINK, single_url):
                        link_type = 'profile'
                        required_role = ROLES_MAP['Account']  # 'account'
                        post_id = clean_url.split('/')[3]
                        # Validate username
                        if not post_id or not re.match(r'^[a-zA-Z0-9._]+$', post_id):
                            results['errors'].append({'url': single_url, 'error': 'Invalid username format'})
                            continue
                    else:
                        results['errors'].append({'url': single_url, 'error': 'Invalid Instagram URL'})
                        continue

                    # Check authorization and apply rate limits for each link
                    # Note: This works with both users-package v4.2.0 (requires role_id) and v4.3.0+ (role_id optional)
                    access_result = self.users_rl.user_access_check(
                        user_id=user_id,
                        role_id=required_role,
                        chat_id=user_id,
                        message_id=f"webui_{link_type}_{idx+1}"
                    )
                    log.debug('[WebUI]: Authorization and rate limit check for user %s link %d (%s): %s', user_id, idx + 1, link_type, access_result)

                    # Check permissions
                    if access_result.get('permissions') != 'allowed':
                        results['errors'].append({'url': single_url, 'error': f"No permission for {link_type} downloads"})
                        log.warning('[WebUI]: User %s denied access to %s (role: %s)', user_id, link_type, required_role)
                        continue

                    # Apply rate limits
                    scheduled_time = datetime.now()
                    rate_limit_time = access_result.get('rate_limits')
                    if rate_limit_time and isinstance(rate_limit_time, datetime):
                        scheduled_time = rate_limit_time
                        log.info('[WebUI]: Rate limit applied for user %s link %d, scheduled for %s', user_id, idx + 1, scheduled_time)

                    # Check uniqueness
                    if not self.database.check_message_uniqueness(post_id=post_id, user_id=user_id):
                        results['errors'].append({'url': single_url, 'error': 'Already in queue or processed'})
                        continue

                    # Create standardized queue message data
                    data = self.database.create_queue_message_data(
                        user_id=user_id,
                        post_id=post_id,
                        post_url=single_url,
                        link_type=link_type,
                        message_id=f"webui_{post_id}",
                        chat_id=user_id,
                        scheduled_time=scheduled_time
                    )

                    self.database.add_message_to_queue(data=data)
                    log.info('[WebUI]: User %s submitted link %d: %s (%s)', user_id, idx + 1, single_url, post_id)

                    results['success'].append({
                        'url': single_url,
                        'post_id': post_id,
                        'scheduled_time': data['scheduled_time']
                    })

                except Exception as error:
                    log.error('[WebUI]: Error processing link %d for user %s: %s', idx + 1, user_id, str(error))
                    results['errors'].append({'url': single_url, 'error': str(error)})

            # Return appropriate response
            total_count = len(results['success']) + len(results['errors'])
            if results['success'] and not results['errors']:
                # All succeeded
                return JSONResponse({
                    'status': 'success',
                    'message': f"{len(results['success'])} link(s) added to queue",
                    'results': results
                })
            elif results['success'] and results['errors']:
                # Partial success
                return JSONResponse({
                    'status': 'partial',
                    'message': f"{len(results['success'])} of {total_count} link(s) added, {len(results['errors'])} failed",
                    'results': results
                }, status_code=207)
            else:
                # All failed
                return JSONResponse({
                    'status': 'error',
                    'message': 'Failed to add any links',
                    'results': results
                }, status_code=400)

        @self.app.get("/queue", response_class=HTMLResponse)
        async def queue_page(
            request: Request,
            page: int = 1,
            limit: int = 20,
            user: dict = Depends(self.get_current_user)
        ):
            """
            Full queue page with pagination.
            
            Query params:
                page (int): Page number (default: 1)
                limit (int): Items per page (default: 20)
            """
            user_id = str(user['id'])
            offset = (page - 1) * limit

            messages = self.database._select(
                table_name='queue',
                columns=('post_id', 'post_url', 'post_owner', 'scheduled_time', 'state', 'download_status', 'upload_status'),
                condition=f"user_id = '{user_id}'",
                order_by='scheduled_time ASC',
                limit=limit,
                offset=offset
            )

            total = self.database._count(table_name='queue', condition=f"user_id = '{user_id}'")

            result = []
            if messages:
                for msg in messages:
                    result.append({
                        'post_id': msg[0],
                        'post_url': msg[1],
                        'post_owner': msg[2],
                        'scheduled_time': msg[3].isoformat() if msg[3] else None,
                        'state': msg[4],
                        'download_status': msg[5],
                        'upload_status': msg[6]
                    })

            context = {
                "request": request,
                "user": user,
                "messages": result,
                "total": total,
                "page": page,
                "limit": limit
            }

            return self.templates.TemplateResponse("queue.html", context)

        @self.app.get("/processed", response_class=HTMLResponse)
        async def processed_page(
            request: Request,
            page: int = 1,
            limit: int = 20,
            user: dict = Depends(self.get_current_user)
        ):
            """
            Full processed page with pagination.

            Query params:
                page (int): Page number (default: 1)
                limit (int): Items per page (default: 20)
            """
            user_id = str(user['id'])
            offset = (page - 1) * limit

            messages = self.database._select(
                table_name='processed',
                columns=('post_id', 'post_url', 'post_owner', 'timestamp', 'state', 'download_status', 'upload_status'),
                condition=f"user_id = '{user_id}'",
                order_by='timestamp DESC',
                limit=limit,
                offset=offset
            )

            total = self.database._count(table_name='processed', condition=f"user_id = '{user_id}'")

            result = []
            if messages:
                for msg in messages:
                    result.append({
                        'post_id': msg[0],
                        'post_url': msg[1],
                        'post_owner': msg[2],
                        'timestamp': msg[3].isoformat() if msg[3] else None,
                        'state': msg[4],
                        'download_status': msg[5],
                        'upload_status': msg[6]
                    })

            # Get statistics by owner
            stats_data = self.database.get_user_processed_stats(user_id=user_id)
            stats = stats_data if stats_data['labels'] else None

            context = {
                "request": request,
                "user": user,
                "messages": result,
                "total": total,
                "page": page,
                "limit": limit,
                "stats": stats
            }

            return self.templates.TemplateResponse("processed.html", context)

        @self.app.get("/accounts", response_class=HTMLResponse)
        async def accounts_page(
            request: Request,
            page: int = 1,
            limit: int = 20,
            sort_by: str = 'last_updated',
            sort_order: str = 'desc',
            user: dict = Depends(self.get_current_user)
        ):
            """
            Accounts page showing Instagram profile metadata.
            Global table (not user-specific).

            Query params:
                page (int): Page number (default: 1)
                limit (int): Items per page (default: 20)
            """
            offset = (page - 1) * limit

            accounts_data = self.database.get_accounts(
                limit=limit,
                offset=offset,
                sort_by=sort_by,
                sort_order=sort_order
            )

            # Convert datetime objects to ISO format for template
            for account in accounts_data['accounts']:
                if account['last_updated']:
                    account['last_updated'] = account['last_updated'].isoformat()

            context = {
                "request": request,
                "user": user,
                "accounts": accounts_data['accounts'],
                "total": accounts_data['counter'],
                "page": page,
                "limit": limit,
                "sort_by": sort_by,
                "sort_order": sort_order
            }

            return self.templates.TemplateResponse("accounts.html", context)

        @self.app.get("/logout")
        async def logout(request: Request):
            """Clear session and redirect to home."""
            request.session.clear()
            return RedirectResponse(url='/')

    def run(self):
        """
        Start the FastAPI web server using uvicorn.
        This method blocks, so run it in a separate thread or process.
        """
        log.info('[WebUI]: Starting web server on %s:%s', self.host, self.port)
        uvicorn.run(self.app, host=self.host, port=self.port, log_level="info")
