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
import io
import json
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4
from urllib.parse import urlparse
from fastapi import FastAPI, Request, HTTPException, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from logger import log
from src.configs.constants import ROLES_MAP
from src.modules.content_processor import RawContentProcessor
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
                uploader (object): Uploader client for WebDAV operations (optional, for content processing)

                Note: raw_content_source_dir and raw_content_dest_dir are NOT configured via kwargs.
                      They are stored in PostgreSQL app_config table and managed via Web UI.
                      ContentProcessor uses hardcoded defaults which are overridden per-user from DB.
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

        # Content processing configuration
        self.uploader = kwargs.get('uploader')

        # Initialize RawContentProcessor if WebDAV client is available
        # Directories are NOT configured here - they come from PostgreSQL app_config per-user
        # Using hardcoded defaults that will be overridden by user config from DB during scan
        self.content_processor = None
        if self.uploader:
            try:
                # Hardcoded defaults - users override via Web UI form saved to PostgreSQL
                default_source_dir = 'data/instagram/__extension-ff'
                default_dest_dir = 'data/instagram'

                self.content_processor = RawContentProcessor(
                    webdav_client=self.uploader.webdav_client,
                    source_dir=default_source_dir,
                    dest_dir=default_dest_dir,
                    database=self.database,
                    # Factory for per-thread clients so raw content can be processed in parallel
                    # (webdav3's shared requests.Session is not thread-safe).
                    client_factory=getattr(self.uploader, 'new_webdav_client', None)
                )
                log.info(
                    '[WebUI]: Content processor initialized with defaults (source=%s, dest=%s). '
                    'Users can override via Web UI configuration form.',
                    default_source_dir, default_dest_dir
                )
            except Exception as e:
                log.warning('[WebUI]: Could not initialize content processor: %s', str(e))
                self.content_processor = None
        else:
            log.warning('[WebUI]: Content processor not initialized - uploader not available')

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

        # Raw content batching settings
        self.raw_scan_limit = int(kwargs.get('raw_scan_limit', webui_secret.get('raw-content-scan-limit', 1000)))
        self.raw_process_batch_size = int(
            kwargs.get('raw_process_batch_size', webui_secret.get('raw-content-process-batch-size', 50))
        )
        # Concurrency for raw content processing. Kept modest by default so Nextcloud is not
        # flooded with parallel WebDAV requests (it locks resources and returns 423 under load).
        self.raw_process_max_workers = max(1, int(
            kwargs.get('raw_process_max_workers', webui_secret.get('raw-content-process-max-workers', 4))
        ))

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

        # Add request logging middleware
        @self.app.middleware("http")
        async def log_requests(request: Request, call_next):
            """Log incoming requests."""
            if '/api/raw-content/item-details' in request.url.path:
                log.debug(f'[WebUI]: {request.method} {request.url.path}')
            response = await call_next(request)
            if '/api/raw-content/item-details' in request.url.path:
                log.debug(f'[WebUI]: Response status={response.status_code}')
            return response

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

    def _build_raw_content_condition(self, user_id: str, exclude_completed: bool = False) -> str:
        """
        Build SQL WHERE condition for raw_content_queue queries.

        Args:
            user_id: User ID to filter by
            exclude_completed: If True, exclude only 'completed' items (keep scanned, processing, error)

        Returns:
            SQL condition string
        """
        condition = f"user_id = '{user_id}'"
        if exclude_completed:
            condition += " AND status = 'scanned'"
        return condition

    def _get_user_raw_processing_dirs(self, user_id: str) -> tuple[Optional[str], Optional[str]]:
        """
        Get user-specific raw processing directory overrides from app_config.

        Returns:
            Tuple of (source_dir_override, dest_dir_override)
        """
        try:
            user_config = self.database.get_user_config(user_id, 'raw_processing')
            if not user_config:
                return None, None

            config_dict = user_config.get('config', {})
            source_dir_override = config_dict.get('source_dir')
            dest_dir_override = config_dict.get('dest_dir')
            return source_dir_override, dest_dir_override
        except Exception as e:
            log.warning('[WebUI]: Failed to read raw_processing config for user %s: %s', user_id, str(e))
            return None, None

    def _derive_nextcloud_base_url(self) -> str:
        """
        Derive the Nextcloud web base URL from the uploader's WebDAV endpoint.

        The WebDAV URL is a DAV endpoint (`https://cloud.example.com/remote.php/dav/files/user`),
        while the WebUI needs the plain web root (`https://cloud.example.com`) to build
        "open this folder in Nextcloud" links. Everything from `/remote.php` (or `/webdav`) onwards
        is stripped, so an instance served from a subpath keeps its prefix. The value is only a
        default: the user can override and persist it via the raw content config form.

        Returns:
            (str) Base URL without a trailing slash, or an empty string if it cannot be derived.
        """
        try:
            webdav_url = (self.uploader.configuration.get('url') or '').strip() if self.uploader else ''
            if not webdav_url:
                return ''

            parsed = urlparse(webdav_url)
            if not parsed.scheme or not parsed.netloc:
                return ''

            path = parsed.path or ''
            for marker in ('/remote.php', '/public.php', '/webdav'):
                index = path.find(marker)
                if index != -1:
                    path = path[:index]
                    break
            else:
                # No DAV marker: the URL points at a plain directory, keep the host only
                path = ''

            return f"{parsed.scheme}://{parsed.netloc}{path.rstrip('/')}"
        except Exception as e:
            log.warning('[WebUI]: Could not derive Nextcloud base URL from the uploader config: %s', str(e))
            return ''

    async def _process_raw_candidates_streaming(
        self,
        user_id: str,
        candidates: list[dict],
        dest_dir_override: Optional[str],
        dedupe_before_process: bool
    ) -> tuple[int, int]:
        """
        Process candidates in parallel and persist each item's terminal status as soon as that item
        finishes, so raw_content_queue (which the WebUI progress poll reads) reflects live progress
        instead of flipping from 'processing' to 'completed' only when the whole batch is done.

        Worker threads just report results through a queue - every DB write stays on the event loop
        thread, because the psycopg pool is a SimpleConnectionPool and is not thread-safe.

        Args:
            user_id: Owner of the queue items.
            candidates: Candidate dicts as built for process_candidates_parallel (must include 'id').
            dest_dir_override: Optional destination directory override.
            dedupe_before_process: If True, dedupe byte-identical files before moving.

        Returns:
            Tuple of (processed_count, error_count).
        """
        if not candidates:
            return (0, 0)

        loop = asyncio.get_running_loop()
        results_queue: asyncio.Queue = asyncio.Queue()

        def on_result(entry: dict) -> None:
            loop.call_soon_threadsafe(results_queue.put_nowait, entry)

        worker_task = asyncio.create_task(asyncio.to_thread(
            self.content_processor.process_candidates_parallel,
            candidates,
            self.raw_process_max_workers,
            dest_dir_override,
            dedupe_before_process,
            on_result
        ))

        counts = {'processed': 0, 'errors': 0}
        handled_ids = set()

        async def apply_results() -> None:
            while True:
                entry = await results_queue.get()
                if entry is None:
                    return
                candidate = entry['candidate']
                result = entry['result']
                item_id = candidate['id']
                item_name = candidate['item_name']
                item_path = candidate['item_path']
                handled_ids.add(item_id)

                try:
                    if result.get('status') == 'success':
                        data = result.get('data', {})
                        self.database.update_raw_content_item_status(
                            item_id=item_id,
                            status='completed',
                            destination=data.get('destination'),
                            files_moved=data.get('files_moved'),
                            error_message=None
                        )
                        self.database.add_raw_item_to_processed(
                            user_id=user_id,
                            item_id=item_id,
                            item_path=item_path,
                            source=data.get('source', 'instagram'),
                            post_id=data.get('post_id', item_name),
                            destination=data.get('destination')
                        )
                        counts['processed'] += 1
                        log.info(
                            '[WebUI]: Item_id=%d completed (%d/%d done)',
                            item_id, counts['processed'] + counts['errors'], len(candidates)
                        )
                    else:
                        error_message = result.get('error', f'Failed to process {item_name}')
                        self.database.update_raw_content_item_status(
                            item_id=item_id,
                            status='error',
                            error_message=error_message
                        )
                        counts['errors'] += 1
                        log.error('[WebUI]: Item_id=%d error: %s', item_id, error_message)
                except Exception as db_error:  # pylint: disable=broad-exception-caught
                    counts['errors'] += 1
                    log.error('[WebUI]: Failed to persist result for item_id=%d: %s', item_id, str(db_error))

        apply_task = asyncio.create_task(apply_results())

        # asyncio.wait() never raises, so the sentinel is always queued and the consumer always exits
        await asyncio.wait([worker_task])
        worker_error = worker_task.exception()
        results_queue.put_nowait(None)
        await apply_task

        if worker_error:
            log.error('[WebUI]: Parallel processing failed: %s', str(worker_error), exc_info=worker_error)

        # Never leave items stuck in 'processing' if the batch died before reporting them.
        for candidate in candidates:
            if candidate['id'] in handled_ids:
                continue
            counts['errors'] += 1
            self.database.update_raw_content_item_status(
                item_id=candidate['id'],
                status='error',
                error_message=f"Processing aborted: {worker_error}" if worker_error else 'Processing aborted without result'
            )
            log.error('[WebUI]: Item_id=%d left unprocessed by the batch - marked as error', candidate['id'])

        return (counts['processed'], counts['errors'])

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

        @self.app.post("/api/retry/{post_id}")
        async def retry_post(
            post_id: str,
            user: dict = Depends(self.get_current_user)
        ):
            """
            Reset the status of a failed post to retry downloading.

            Args:
                post_id (str): The ID of the post to retry.

            Returns:
                JSONResponse: Success or error message.
            """
            user_id = str(user['id'])

            # Verify the post belongs to this user
            existing = self.database._select(
                table_name='queue',
                columns=('user_id', 'state', 'download_status', 'upload_status'),
                condition=f"post_id = '{post_id}'",
                limit=1
            )

            if not existing:
                return JSONResponse({
                    'status': 'error',
                    'message': 'Post not found in queue'
                }, status_code=404)

            if existing[0][0] != user_id:
                return JSONResponse({
                    'status': 'error',
                    'message': 'Not authorized to retry this post'
                }, status_code=403)

            # Check if post is actually in error state
            state, download_status, upload_status = existing[0][1], existing[0][2], existing[0][3]
            is_error = state == 'error' or download_status == 'download_error' or upload_status == 'upload_error'

            if not is_error:
                return JSONResponse({
                    'status': 'error',
                    'message': 'Post is not in error state'
                }, status_code=400)

            try:
                # Reset statuses to initial state
                self.database.update_message_state_in_queue(
                    post_id=post_id,
                    state='waiting',
                    download_status='not started',
                    upload_status='not started'
                )

                # Reschedule to now
                self.database.update_schedule_time_in_queue(
                    post_id=post_id,
                    user_id=user_id,
                    scheduled_time=datetime.now()
                )

                log.info(f"[webui] Post {post_id} reset for retry by user {user_id}")

                return JSONResponse({
                    'status': 'success',
                    'message': 'Post reset successfully, will be retried soon'
                })

            except Exception as e:
                log.error(f"[webui] Failed to retry post {post_id}: {e}")
                return JSONResponse({
                    'status': 'error',
                    'message': f'Failed to reset post: {str(e)}'
                }, status_code=500)

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

        @self.app.get("/raw-content", response_class=HTMLResponse)
        async def raw_content_page(
            request: Request,
            page: int = 1,
            limit: int = 50,
            user: dict = Depends(self.get_current_user)
        ):
            """
            Raw content scan/process page with dedicated batch controls.
            """
            user_id = str(user['id'])
            offset = (page - 1) * limit

            items = self.database.get_user_raw_content_items(
                user_id=user_id,
                status=None,
                limit=limit,
                offset=offset
            )

            total = self.database._count(table_name='raw_content_queue', condition=f"user_id = '{user_id}'")
            stats = self.database.get_user_raw_content_stats(user_id=user_id)

            context = {
                "request": request,
                "user": user,
                "items": items,
                "total": total,
                "page": page,
                "limit": limit,
                "stats": stats,
                "content_processor_enabled": bool(self.content_processor),
                "default_scan_limit": self.raw_scan_limit,
                "default_batch_size": self.raw_process_batch_size
            }
            return self.templates.TemplateResponse("raw_content.html", context)

        @self.app.post("/api/raw-content/scan")
        async def scan_raw_content(
            request: Request,
            limit: Optional[int] = None,
            clear_all: Optional[bool] = False,
            new_format_only: Optional[bool] = False,
            user: dict = Depends(self.get_current_user)
        ):
            """
            Scan only: reads source directory and stores candidates into raw_content_queue.

            Args:
                limit: Maximum items to scan (default from config)
                clear_all: If True, clear ALL queue items before scan (including errors/completed)
                new_format_only: If True, scan only for Firefox Extension format (grouped mode with metadata.txt/json)
            """
            if not self.content_processor:
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "error",
                        "message": "Raw content processing is not configured on this instance",
                        "details": None
                    }
                )

            user_id = str(user['id'])
            scan_limit = max(1, min(int(limit or self.raw_scan_limit), 10000))

            log.info(
                '[WebUI]: Starting raw content scan for user %s (limit=%d, source_dir=%s, new_format_only=%s)',
                user_id, scan_limit, self.content_processor.source_dir, new_format_only
            )

            try:
                scan_id = str(uuid4())
                log.debug('[WebUI]: Generated scan_id=%s', scan_id)

                # Clear queue items for fresh scan
                clear_mode = "ALL items" if clear_all else "scanned/processing items"
                log.info('[WebUI]: Clearing %s for user %s', clear_mode, user_id)
                cleared = self.database.clear_raw_content_scanned_items(user_id=user_id, clear_all=clear_all)
                log.info('[WebUI]: Cleared %d items', cleared)

                # Load user-specific config (directories) if available
                source_dir_override, dest_dir_override = self._get_user_raw_processing_dirs(user_id)
                if source_dir_override or dest_dir_override:
                    log.info(
                        '[WebUI]: Using user-specific raw_processing config for user %s (source_dir_override=%s, dest_dir_override=%s)',
                        user_id, source_dir_override, dest_dir_override
                    )

                # Apply filter if new_format_only is enabled
                scan_kwargs = {
                    'limit': scan_limit,
                    'offset': 0,
                    'user_id': user_id,
                    'database': self.database
                }
                if new_format_only:
                    log.info('[WebUI]: Filtering scan to new format only (grouped mode)')
                    scan_kwargs['new_format_only'] = True
                if source_dir_override:
                    scan_kwargs['source_dir_override'] = source_dir_override
                if dest_dir_override:
                    scan_kwargs['dest_dir_override'] = dest_dir_override

                log.info('[WebUI]: Calling content_processor.scan_source(**%s)', list(scan_kwargs.keys()))
                scan_result = self.content_processor.scan_source(**scan_kwargs)
                log.debug('[WebUI]: scan_source returned status=%s, processable=%d',
                          scan_result.get('status'), scan_result.get('processable_count', 0))

                if scan_result.get('status') == 'error':
                    log.error('[WebUI]: Scan source returned error: %s', scan_result.get('errors'))
                    return JSONResponse(
                        status_code=400,
                        content={
                            "status": "error",
                            "message": "Scan failed",
                            "details": scan_result
                        }
                    )

                log.debug('[WebUI]: Upserting %d processable items to database', len(scan_result.get('processable_items', [])))
                upsert_result = self.database.upsert_raw_content_scan_items(
                    user_id=user_id,
                    items=scan_result.get('processable_items', []),
                    scan_id=scan_id
                )
                log.debug('[WebUI]: Upsert result: inserted=%d, updated=%d',
                          upsert_result.get('inserted', 0), upsert_result.get('updated', 0))

                stats = self.database.get_user_raw_content_stats(user_id=user_id)
                log.debug('[WebUI]: User stats after scan: %s', stats)

                log.info(
                    '[WebUI]: User %s scanned raw content: processable=%d, inserted=%d, updated=%d',
                    user_id,
                    scan_result.get('processable_count', 0),
                    upsert_result.get('inserted', 0),
                    upsert_result.get('updated', 0)
                )

                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "success",
                        "message": (
                            f"Scan complete: {scan_result.get('processable_count', 0)} candidates found "
                            f"(inserted {upsert_result.get('inserted', 0)}, updated {upsert_result.get('updated', 0)})"
                        ),
                        "details": {
                            "scan_id": scan_id,
                            "cleared_scanned": cleared,
                            "total_items": scan_result.get('total_items', 0),
                            "scanned_items": scan_result.get('scanned_items', 0),
                            "processable_count": scan_result.get('processable_count', 0),
                            "skipped_count": scan_result.get('skipped_count', 0),
                            "inserted": upsert_result.get('inserted', 0),
                            "updated": upsert_result.get('updated', 0),
                            "stats": stats
                        }
                    }
                )
            except Exception as e:
                log.error('[WebUI]: Raw content scan failed for user %s: %s', user_id, str(e), exc_info=True)
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "error",
                        "message": f"Scan failed: {str(e)}",
                        "details": {"exception_type": type(e).__name__}
                    }
                )

        @self.app.get("/api/raw-content/stats")
        async def get_raw_content_stats(
            request: Request,
            user: dict = Depends(self.get_current_user)
        ):
            """
            Get current raw content queue statistics for the user.
            """
            if not self.content_processor:
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "error",
                        "message": "Raw content processing is not configured"
                    }
                )

            user_id = str(user['id'])
            try:
                stats = self.database.get_user_raw_content_stats(user_id=user_id)
                return JSONResponse(
                    status_code=200,
                    content=stats
                )
            except Exception as e:
                log.error('[WebUI]: Failed to get raw content stats for user %s: %s', user_id, str(e))
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "error",
                        "message": f"Failed to get stats: {str(e)}"
                    }
                )

        @self.app.get("/api/raw-content/config")
        async def get_raw_content_config(
            request: Request,
            user: dict = Depends(self.get_current_user)
        ):
            """
            Get raw content directory configuration for the user.
            Returns stored source_dir and dest_dir, or defaults from processor.
            The Nextcloud base URL falls back to the one derived from the bot's WebDAV endpoint.
            """
            user_id = str(user['id'])
            try:
                # Get stored config from database
                config_data = self.database.get_user_config(user_id=user_id, component='raw_processing')
                config = config_data.get('config', {})

                # If no config in DB, return current processor settings
                if not config and self.content_processor:
                    config = {
                        'source_dir': self.content_processor.source_dir,
                        'dest_dir': self.content_processor.dest_dir
                    }

                # Auto-discovered default: only used until the user saves an explicit override
                if not config.get('nc_base_url'):
                    config = dict(config)
                    config['nc_base_url'] = self._derive_nextcloud_base_url()

                return JSONResponse(
                    status_code=200,
                    content=config
                )
            except Exception as e:
                log.error('[WebUI]: Failed to get raw content config for user %s: %s', user_id, str(e))
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "error",
                        "message": f"Failed to get config: {str(e)}"
                    }
                )

        @self.app.post("/api/raw-content/config")
        async def set_raw_content_config(
            request: Request,
            user: dict = Depends(self.get_current_user)
        ):
            """
            Set raw content directory configuration for the user.
            Stores source_dir and dest_dir in app_config table for persistent use.
            """
            if not self.content_processor:
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "error",
                        "message": "Raw content processing is not configured"
                    }
                )

            user_id = str(user['id'])
            try:
                body = await request.json()
                source_dir = body.get('source_dir', '').strip()
                dest_dir = body.get('dest_dir', '').strip()
                nc_base_url = (body.get('nc_base_url') or '').strip().rstrip('/')

                if not source_dir or not dest_dir:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "status": "error",
                            "message": "Both source_dir and dest_dir are required"
                        }
                    )

                # Empty is allowed and simply disables the "open in Nextcloud" links
                if nc_base_url:
                    parsed_nc = urlparse(nc_base_url)
                    if parsed_nc.scheme not in ('http', 'https') or not parsed_nc.netloc:
                        return JSONResponse(
                            status_code=400,
                            content={
                                "status": "error",
                                "message": "nc_base_url must be an http(s) URL, for example https://cloud.example.com"
                            }
                        )

                # Update database config using generic app_config table
                self.database.set_user_config(
                    user_id=user_id,
                    component='raw_processing',
                    config={
                        'source_dir': source_dir,
                        'dest_dir': dest_dir,
                        'nc_base_url': nc_base_url
                    }
                )

                log.info('[WebUI]: Updated raw_processing config for user %s: source=%s, dest=%s, nc_base_url=%s',
                         user_id, source_dir, dest_dir, nc_base_url or '-')

                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "success",
                        "message": "Configuration updated successfully",
                        "config": {
                            "source_dir": source_dir,
                            "dest_dir": dest_dir,
                            "nc_base_url": nc_base_url
                        }
                    }
                )
            except Exception as e:
                log.error('[WebUI]: Failed to set raw content config for user %s: %s', user_id, str(e))
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "error",
                        "message": f"Failed to set config: {str(e)}"
                    }
                )

        @self.app.post("/api/raw-content/item/{item_id}")
        async def update_raw_content_item(
            request: Request,
            item_id: int,
            user: dict = Depends(self.get_current_user)
        ):
            """
            Manually edit metadata fields (owner/post_id/post_url/source) of a queue item.

            Lets the operator fix values the app could not extract without re-scanning; processing
            reads these values directly from the queue.
            """
            user_id = str(user['id'])
            try:
                body = await request.json()
                editable = ('post_owner', 'post_id', 'post_url', 'source')
                fields = {k: body[k] for k in editable if k in body}
                if not fields:
                    return JSONResponse(
                        status_code=400,
                        content={"status": "error", "message": f"No editable fields provided (allowed: {', '.join(editable)})"}
                    )

                updated = self.database.update_raw_content_item_fields(item_id=item_id, user_id=user_id, fields=fields)
                if not updated:
                    return JSONResponse(
                        status_code=404,
                        content={"status": "error", "message": f"Item {item_id} not found for this user"}
                    )

                log.info('[WebUI]: User %s edited raw content item %d fields: %s', user_id, item_id, list(fields.keys()))
                return JSONResponse(
                    status_code=200,
                    content={"status": "success", "message": "Item updated", "item_id": item_id, "updated_fields": fields}
                )
            except Exception as e:
                log.error('[WebUI]: Failed to update raw content item %d for user %s: %s', item_id, user_id, str(e))
                return JSONResponse(
                    status_code=500,
                    content={"status": "error", "message": f"Failed to update item: {str(e)}"}
                )

        @self.app.get("/api/raw-content/item-details/{item_id}")
        async def get_raw_content_item_details(
            request: Request,
            item_id: int,
            user: dict = Depends(self.get_current_user)
        ):
            """
            Get details about a raw content queue item including files in its directory.
            """
            if not self.content_processor:
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "error",
                        "message": "Raw content processing is not configured"
                    }
                )

            if not self.content_processor.webdav_client:
                log.error('[WebUI]: WebDAV client not initialized in content_processor')
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "error",
                        "message": "WebDAV client not configured"
                    }
                )

            user_id = str(user['id'])
            try:
                # Get item from database
                item = self.database._select(
                    table_name='raw_content_queue',
                    columns=('id', 'item_name', 'item_path', 'mode', 'status'),
                    condition=f"id = {item_id} AND user_id = '{user_id}'"
                )

                if not item:
                    return JSONResponse(
                        status_code=404,
                        content={
                            "status": "error",
                            "message": "Item not found"
                        }
                    )

                item_data = {
                    'id': item[0][0],
                    'item_name': item[0][1],
                    'item_path': item[0][2],
                    'mode': item[0][3],
                    'status': item[0][4],
                    'metadata_file': None,
                    'content_files': [],
                    'files': []
                }

                # Try to list files in the directory/file
                try:
                    log.info('[WebUI]: Item %d mode=%s, name=%s, path=%s', item_id, item_data['mode'], item_data['item_name'], item_data['item_path'])

                    if item_data['mode'] != 'grouped':
                        return JSONResponse(
                            status_code=400,
                            content={'error': f"Unsupported item mode: {item_data['mode']}. Only 'grouped' mode is supported."}
                        )

                    # For grouped mode, list files in the directory
                    log.info('[WebUI]: [GROUPED] Item path: %s', repr(item_data['item_path']))
                    log.info('[WebUI]: [GROUPED] Attempting to list directory')
                    try:
                        raw_list = self.content_processor.webdav_client.list(item_data['item_path'])
                        log.info('[WebUI]: [GROUPED] list() returned type: %s', type(raw_list).__name__)
                        log.info('[WebUI]: [GROUPED] list() returned length: %d', len(raw_list) if raw_list else 0)

                        if raw_list:
                            log.info('[WebUI]: [GROUPED] First 3 raw items:')
                            for i, item in enumerate(raw_list[:3]):
                                log.info('[WebUI]: [GROUPED]   [%d] type=%s, value=%s', i, type(item).__name__, repr(item))

                        files = raw_list
                    except Exception as list_error:
                        log.error('[WebUI]: [GROUPED] list() EXCEPTION: %s', str(list_error), exc_info=True)
                        files = []

                    metadata_file = None
                    content_files = []

                    if files:
                        for idx, file_entry in enumerate(files):
                            log.debug('[WebUI]: [GROUPED] [%d] Raw entry: %s (type: %s)', idx, str(file_entry), type(file_entry).__name__)
                            fname = self.content_processor._normalize_webdav_name(file_entry)
                            log.debug('[WebUI]: [GROUPED] [%d] Normalized: %s', idx, fname)

                            if fname:
                                if fname in ('metadata.json', 'metadata.txt'):
                                    metadata_file = fname
                                    log.info('[WebUI]: [GROUPED] Found metadata: %s', fname)
                                elif fname == item_data['item_name']:
                                    # Skip the directory reference itself (parent directory name)
                                    log.debug('[WebUI]: [GROUPED] Skipping directory reference: %s', fname)
                                else:
                                    content_files.append(fname)
                    else:
                        log.warning('[WebUI]: [GROUPED] No files to process - files list is empty!')

                    item_data['metadata_file'] = metadata_file
                    item_data['content_files'] = sorted(content_files)
                    item_data['files'] = ([metadata_file] if metadata_file else []) + item_data['content_files']

                    log.info('[WebUI]: [GROUPED FINAL] metadata=%s, content_files=%d, files=%d',
                             metadata_file, len(content_files), len(item_data['files']))
                    if content_files:
                        log.info('[WebUI]: [GROUPED FINAL] Sample content files: %s', content_files[:5])

                    # For grouped mode, also try to parse metadata if found
                    if metadata_file:
                        try:
                            metadata_path = f"{item_data['item_path']}/{metadata_file}"
                            log.info('[WebUI]: [GROUPED] Downloading metadata from: %s', metadata_path)
                            buffer = io.BytesIO()
                            self.content_processor.webdav_client.download_from(
                                buff=buffer,
                                remote_path=metadata_path
                            )
                            metadata_content = buffer.getvalue().decode('utf-8', errors='ignore')
                            log.info('[WebUI]: [GROUPED] Downloaded %d bytes of metadata', len(metadata_content))

                            parsed = self.content_processor._parse_metadata(metadata_content, metadata_file)
                            log.info('[WebUI]: [GROUPED] Parsed metadata keys: %s',
                                     list(parsed.keys()))

                            # If metadata has files list, use it (for reference, but grouped mode already lists all files)
                            parsed_files = parsed.get('files', []) or []
                            if isinstance(parsed_files, str):
                                parsed_files = [parsed_files]
                            if parsed_files:
                                log.info('[WebUI]: [GROUPED] Metadata specifies %d files: %s', len(parsed_files), parsed_files[:5])
                        except Exception as parse_error:
                            log.warning('[WebUI]: [GROUPED] Could not parse metadata: %s',
                                        str(parse_error), exc_info=True)

                except Exception as e:
                    log.warning('[WebUI]: Could not list files for item %d: %s', item_id, str(e))
                    item_data['metadata_file'] = None
                    item_data['content_files'] = []
                    item_data['files'] = []

                log.info('[WebUI]: RETURNING for item %d: metadata=%s, content_files=%d, files=%d',
                         item_id, item_data['metadata_file'], len(item_data['content_files']), len(item_data['files']))
                log.info('[WebUI]: Item data keys: %s', list(item_data.keys()))
                log.info('[WebUI]: Item data: %s', item_data)

                return JSONResponse(
                    status_code=200,
                    content=item_data
                )
            except Exception as e:
                log.error('[WebUI]: Failed to get item details for user %s: %s', user_id, str(e))
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "error",
                        "message": f"Failed to get item details: {str(e)}"
                    }
                )

        @self.app.get("/api/raw-content/queue")
        async def get_raw_content_queue(
            request: Request,
            offset: int = 0,
            limit: int = 20,
            exclude_completed: bool = False,
            user: dict = Depends(self.get_current_user)
        ):
            """
            Get paginated raw content queue items for the user.

            Args:
                offset: Pagination offset
                limit: Items per page
                exclude_completed: If True, exclude items with status='completed'
            """
            if not self.content_processor:
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "error",
                        "message": "Raw content processing is not configured"
                    }
                )

            user_id = str(user['id'])
            try:
                offset = max(0, int(offset))
                limit = max(1, min(int(limit), 100))

                # Get items with optional exclusion of completed items
                items = self.database._select(
                    table_name='raw_content_queue',
                    columns=(
                        'id', 'item_name', 'item_path', 'mode', 'post_id',
                        'post_url', 'post_owner', 'source', 'status',
                        'scan_id', 'destination', 'files_moved', 'error_message',
                        'scanned_at', 'started_at', 'finished_at', 'updated_at', 'content_files'
                    ),
                    condition=self._build_raw_content_condition(user_id, exclude_completed),
                    order_by='id ASC',
                    limit=limit,
                    offset=offset
                )

                total = self.database._count(
                    table_name='raw_content_queue',
                    condition=self._build_raw_content_condition(user_id, exclude_completed)
                )

                # Format items for JSON response
                formatted_items = []
                if items:  # Handle None or empty result
                    for item in items:
                        content_files = []
                        try:
                            if item[17] and isinstance(item[17], str):
                                content_files = json.loads(item[17])
                        except (json.JSONDecodeError, ValueError):
                            pass

                        formatted_items.append({
                            'id': item[0],
                            'item_name': item[1],
                            # Needed by the WebUI to build the "open this folder in Nextcloud" link
                            'item_path': item[2],
                            'mode': item[3],
                            'post_id': item[4],
                            'post_url': item[5],
                            'post_owner': item[6],
                            'source': item[7],
                            'status': item[8],
                            'files_moved': item[11],
                            'error_message': item[12],
                            'updated_at': item[16].isoformat() if item[16] else None,
                            'content_files': content_files
                        })

                return JSONResponse(
                    status_code=200,
                    content={
                        'items': formatted_items,
                        'total': total or 0,
                        'offset': offset,
                        'limit': limit
                    }
                )
            except Exception as e:
                log.error('[WebUI]: Failed to get raw content queue for user %s: %s', user_id, str(e))
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "error",
                        "message": f"Failed to get queue: {str(e)}"
                    }
                )

        @self.app.get("/api/raw-content/processed")
        async def get_raw_content_processed(
            request: Request,
            offset: int = 0,
            limit: int = 20,
            user: dict = Depends(self.get_current_user)
        ):
            """
            Get paginated raw content processed (completed) items for the user.
            """
            if not self.content_processor:
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "error",
                        "message": "Raw content processing is not configured"
                    }
                )

            user_id = str(user['id'])
            try:
                offset = max(0, int(offset))
                limit = max(1, min(int(limit), 100))

                # Get only completed items
                condition = f"user_id = '{user_id}' AND status = 'completed'"

                items = self.database._select(
                    table_name='raw_content_queue',
                    columns=(
                        'id', 'item_name', 'item_path', 'mode', 'status',
                        'scan_id', 'destination', 'files_moved', 'error_message',
                        'scanned_at', 'started_at', 'finished_at', 'updated_at'
                    ),
                    condition=condition,
                    order_by='updated_at DESC',
                    limit=limit,
                    offset=offset
                )

                total = self.database._count(
                    table_name='raw_content_queue',
                    condition=condition
                )

                # Format items for JSON response
                formatted_items = []
                if items:
                    for item in items:
                        formatted_items.append({
                            'id': item[0],
                            'item_name': item[1],
                            'item_path': item[2],
                            'mode': item[3],
                            'status': item[4],
                            'files_moved': item[7],
                            'destination': item[6],
                            'updated_at': item[12].isoformat() if item[12] else None
                        })

                return JSONResponse(
                    status_code=200,
                    content={
                        'items': formatted_items,
                        'total': total,
                        'offset': offset,
                        'limit': limit
                    }
                )
            except Exception as e:
                log.error('[WebUI]: Failed to get raw content processed for user %s: %s', user_id, str(e))
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "error",
                        "message": f"Failed to get processed items: {str(e)}"
                    }
                )

        @self.app.get("/api/raw-content/legacy-errors")
        async def get_raw_content_legacy_errors(
            request: Request,
            offset: int = 0,
            limit: int = 50,
            user: dict = Depends(self.get_current_user)
        ):
            """
            Temporary helper endpoint for legacy recovery.

            Lists files currently located in instagram root directory and enriches each file
            with matching rows from processed table.
            """
            if not self.content_processor:
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "error",
                        "message": "Raw content processing is not configured"
                    }
                )

            user_id = str(user['id'])
            try:
                offset = max(0, int(offset))
                limit = max(1, min(int(limit), 200))

                # Prefer explicit instagram root under destination, fallback to destination root.
                legacy_root_candidates = [
                    f"{self.content_processor.dest_dir}/instagram",
                    self.content_processor.dest_dir
                ]

                root_files = []
                selected_root = None
                for candidate in legacy_root_candidates:
                    try:
                        listed = self.content_processor.webdav_client.list(candidate)
                        normalized = [
                            self.content_processor._normalize_webdav_name(x)
                            for x in (listed or [])
                        ]
                        normalized = [x for x in normalized if x]

                        # Keep legacy root scan lightweight:
                        # avoid expensive per-item WebDAV _is_directory checks (can trigger many network calls)
                        # and include only likely file names.
                        files_only = [
                            name for name in normalized
                            if ('.' in name and not name.startswith('.'))
                        ]

                        if files_only:
                            selected_root = candidate
                            root_files = sorted(files_only)
                            break
                    except Exception:
                        continue

                total = len(root_files)
                paged_files = root_files[offset:offset + limit]

                def _escape(value: str) -> str:
                    return value.replace("'", "''")

                items = []
                for filename in paged_files:
                    basename = filename.rsplit('.', 1)[0]
                    filename_sql = _escape(filename)
                    basename_sql = _escape(basename)

                    processed_rows = self.database._select(
                        table_name='processed',
                        columns=(
                            'id', 'user_id', 'post_id', 'post_url', 'post_owner',
                            'link_type', 'message_id', 'chat_id',
                            'download_status', 'upload_status', 'timestamp', 'state'
                        ),
                        condition=(
                            f"user_id = '{user_id}' AND ("
                            f"post_url LIKE '%{filename_sql}%' OR "
                            f"post_id LIKE '%{basename_sql}%')"
                        ),
                        order_by='timestamp DESC',
                        limit=10
                    )

                    data = []
                    if processed_rows:
                        for row in processed_rows:
                            post_id = row[2]
                            post_link = None
                            if post_id and str(post_id).strip():
                                post_link = f"https://www.instagram.com/p/{str(post_id).strip()}/"

                            data.append({
                                'id': row[0],
                                'user_id': row[1],
                                'post_id': post_id,
                                'post_link': post_link,
                                'post_url': row[3],
                                'post_owner': row[4],
                                'link_type': row[5],
                                'message_id': row[6],
                                'chat_id': row[7],
                                'download_status': row[8],
                                'upload_status': row[9],
                                'timestamp': row[10].isoformat() if row[10] else None,
                                'state': row[11]
                            })

                    items.append({
                        'filename': filename,
                        'data': data
                    })

                return JSONResponse(
                    status_code=200,
                    content={
                        'root': selected_root,
                        'items': items,
                        'total': total,
                        'offset': offset,
                        'limit': limit
                    }
                )
            except Exception as e:
                log.error('[WebUI]: Failed to get legacy errors for user %s: %s', user_id, str(e), exc_info=True)
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "error",
                        "message": f"Failed to get legacy errors: {str(e)}"
                    }
                )

        @self.app.post("/api/raw-content/legacy-errors/cleanup")
        async def cleanup_raw_content_legacy_error(
            request: Request,
            user: dict = Depends(self.get_current_user)
        ):
            """
            Cleanup helper for legacy artifacts.

            Deletes a file from legacy Nextcloud root and removes matching rows from processed table.
            """
            if not self.content_processor:
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "error",
                        "message": "Raw content processing is not configured"
                    }
                )

            user_id = str(user['id'])
            try:
                body = await request.json()
                filename = str(body.get('filename', '')).strip()
                root = str(body.get('root', '')).strip()
                processed_ids = body.get('processed_ids') or []

                if not filename:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "status": "error",
                            "message": "filename is required"
                        }
                    )

                if '/' in filename or '\\' in filename:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "status": "error",
                            "message": "filename must not contain path separators"
                        }
                    )

                legacy_root_candidates = [
                    f"{self.content_processor.dest_dir}/instagram",
                    self.content_processor.dest_dir
                ]

                file_deleted = False
                deleted_path = None

                if root and root in legacy_root_candidates:
                    roots_to_try = [root] + [r for r in legacy_root_candidates if r != root]
                else:
                    roots_to_try = legacy_root_candidates

                for candidate_root in roots_to_try:
                    target_path = f"{candidate_root.rstrip('/')}/{filename}"
                    try:
                        if self.content_processor.webdav_client.check(target_path):
                            self.content_processor.webdav_client.clean(target_path)
                            file_deleted = True
                            deleted_path = target_path
                            log.info('[WebUI]: Legacy cleanup removed file for user %s: %s', user_id, target_path)
                            break
                    except Exception:
                        continue

                # Remove rows from processed table
                db_deleted_count = 0
                if processed_ids and isinstance(processed_ids, list):
                    safe_ids = [int(x) for x in processed_ids if str(x).isdigit()]
                    if safe_ids:
                        ids_sql = ','.join(str(x) for x in safe_ids)
                        to_delete_rows = self.database._select(
                            table_name='processed',
                            columns=('id',),
                            condition=f"user_id = '{user_id}' AND id IN ({ids_sql})"
                        )
                        db_deleted_count = len(to_delete_rows or [])
                        self.database._delete(
                            table_name='processed',
                            condition=f"user_id = '{user_id}' AND id IN ({ids_sql})"
                        )
                else:
                    filename_sql = filename.replace("'", "''")
                    basename_sql = filename.rsplit('.', 1)[0].replace("'", "''")
                    to_delete_rows = self.database._select(
                        table_name='processed',
                        columns=('id',),
                        condition=(
                            f"user_id = '{user_id}' AND ("
                            f"post_url LIKE '%{filename_sql}%' OR "
                            f"post_id LIKE '%{basename_sql}%')"
                        )
                    )
                    db_deleted_count = len(to_delete_rows or [])
                    self.database._delete(
                        table_name='processed',
                        condition=(
                            f"user_id = '{user_id}' AND ("
                            f"post_url LIKE '%{filename_sql}%' OR "
                            f"post_id LIKE '%{basename_sql}%')"
                        )
                    )

                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "success",
                        "message": "Legacy artifact cleanup completed",
                        "file_deleted": file_deleted,
                        "deleted_path": deleted_path,
                        "db_deleted_count": db_deleted_count
                    }
                )
            except Exception as e:
                log.error('[WebUI]: Failed to cleanup legacy artifact for user %s: %s', user_id, str(e), exc_info=True)
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "error",
                        "message": f"Failed to cleanup legacy artifact: {str(e)}"
                    }
                )

        @self.app.post("/api/raw-content/process")
        async def process_raw_content_batch(
            request: Request,
            batch_size: Optional[int] = None,
            dedupe_before_process: bool = True,
            user: dict = Depends(self.get_current_user)
        ):
            """
            Process scanned raw content in batches from raw_content_queue table.
            Runs processing in background to avoid timeout.
            """
            if not self.content_processor:
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "error",
                        "message": "Raw content processing is not configured on this instance",
                        "details": None
                    }
                )

            user_id = str(user['id'])
            effective_batch_size = max(1, min(int(batch_size or self.raw_process_batch_size), 1000))
            _, dest_dir_override = self._get_user_raw_processing_dirs(user_id)

            log.info('[WebUI]: Starting raw content batch processing for user %s (batch_size=%d)', user_id, effective_batch_size)

            # Run processing in background to avoid timeout
            async def process_batch_background():
                try:
                    log.debug('[WebUI]: Fetching scanned items from database')
                    batch_items = self.database.get_user_raw_content_items(
                        user_id=user_id,
                        status='scanned',
                        limit=effective_batch_size,
                        offset=0
                    )
                    log.info('[WebUI]: Retrieved %d scanned items from database for processing', len(batch_items))

                    if not batch_items:
                        log.info('[WebUI]: No scanned items found.')
                        return

                    # Build candidates (parse content_files once) and mark them 'processing'.
                    candidates = []
                    for item in batch_items:
                        content_files_json = item.get('content_files', '[]')
                        content_files = []
                        if content_files_json:
                            try:
                                if isinstance(content_files_json, str):
                                    content_files = json.loads(content_files_json)
                                else:
                                    content_files = content_files_json
                            except (json.JSONDecodeError, ValueError):
                                content_files = []
                        candidates.append({
                            'id': item['id'],
                            'item_name': item['item_name'],
                            'item_path': item['item_path'],
                            'mode': item['mode'],
                            'content_files': content_files,
                            'post_owner': item.get('post_owner'),
                            'post_id': item.get('post_id'),
                            'source': item.get('source')
                        })
                        self.database.update_raw_content_item_status(item_id=item['id'], status='processing')

                    # Process candidates concurrently (one WebDAV client per worker). File I/O runs
                    # off the event loop; each item's status is written as soon as it finishes.
                    processed_count, error_count = await self._process_raw_candidates_streaming(
                        user_id=user_id,
                        candidates=candidates,
                        dest_dir_override=dest_dir_override,
                        dedupe_before_process=dedupe_before_process
                    )

                    log.info('[WebUI]: Batch processing complete: processed=%d, errors=%d', processed_count, error_count)
                except Exception as e:
                    log.error('[WebUI]: Background batch processing failed for user %s: %s', user_id, str(e), exc_info=True)

            # Start background task
            asyncio.create_task(process_batch_background())

            # Return immediately with stats
            try:
                remaining_scanned = self.database.count_raw_content_items(user_id=user_id, status='scanned')
                stats = self.database.get_user_raw_content_stats(user_id=user_id)

                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "processing",
                        "message": f"Batch processing started (items: {remaining_scanned})",
                        "details": {
                            "batch_size": effective_batch_size,
                            "queued_items": remaining_scanned,
                            "stats": stats
                        }
                    }
                )
            except Exception as e:
                log.error('[WebUI]: Failed to return immediate response for batch processing: %s', str(e))
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "error",
                        "message": f"Failed to start batch processing: {str(e)}",
                        "details": None
                    }
                )

        @self.app.post("/api/raw-content/process-item/{item_id}")
        async def process_raw_content_item(
            request: Request,
            item_id: int,
            dedupe_before_process: bool = True,
            user: dict = Depends(self.get_current_user)
        ):
            """
            Process a single raw content queue item.
            Can be called from UI to test processing of a specific item.
            """
            if not self.content_processor:
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "error",
                        "message": "Raw content processing is not configured on this instance",
                        "details": None
                    }
                )

            user_id = str(user['id'])
            _, dest_dir_override = self._get_user_raw_processing_dirs(user_id)
            log.info('[WebUI]: Processing single item_id=%d for user %s', item_id, user_id)

            try:
                # Get item from database
                item = self.database._select(
                    table_name='raw_content_queue',
                    columns=('id', 'item_name', 'item_path', 'mode', 'status', 'content_files', 'post_id', 'post_owner', 'source'),
                    condition=f"id = {item_id} AND user_id = '{user_id}'"
                )

                if not item:
                    log.warning('[WebUI]: Item not found: item_id=%d, user_id=%s', item_id, user_id)
                    return JSONResponse(
                        status_code=404,
                        content={
                            "status": "error",
                            "message": f"Item {item_id} not found",
                            "details": None
                        }
                    )

                item_rec = item[0]
                item_name = item_rec[1]
                item_path = item_rec[2]
                mode = item_rec[3]
                content_files_json = item_rec[5] if len(item_rec) > 5 else '[]'
                item_post_id = item_rec[6] if len(item_rec) > 6 else None
                item_post_owner = item_rec[7] if len(item_rec) > 7 else None
                item_source = item_rec[8] if len(item_rec) > 8 else None

                # Parse content_files from JSON
                content_files = []
                if content_files_json:
                    try:
                        if isinstance(content_files_json, str):
                            content_files = json.loads(content_files_json)
                        else:
                            content_files = content_files_json
                    except (json.JSONDecodeError, ValueError):
                        content_files = []

                log.info('[WebUI]: Processing item_id=%d, name=%s, mode=%s, files=%d, path=%s',
                         item_id, item_name, mode, len(content_files), item_path)

                # Update status to processing
                self.database.update_raw_content_item_status(item_id=item_id, status='processing')

                # Process the item off the event loop - one post can take minutes of WebDAV
                # work, and blocking here would freeze every other request (including the
                # progress polls) for that whole time.
                result = await asyncio.to_thread(
                    self.content_processor.process_candidate,
                    item_path=item_path,
                    item_name=item_name,
                    mode=mode,
                    content_files=content_files,
                    post_owner=item_post_owner,
                    post_id=item_post_id,
                    source=item_source,
                    dest_dir_override=dest_dir_override,
                    dedupe_before_process=dedupe_before_process
                )

                if result.get('status') == 'success':
                    log.info('[WebUI]: Item_id=%d processed successfully', item_id)
                    data = result.get('data', {})
                    self.database.update_raw_content_item_status(
                        item_id=item_id,
                        status='completed',
                        destination=data.get('destination'),
                        files_moved=data.get('files_moved'),
                        error_message=None
                    )
                    self.database.add_raw_item_to_processed(
                        user_id=user_id,
                        item_id=item_id,
                        item_path=item_path,
                        source=data.get('source', 'instagram'),
                        post_id=data.get('post_id', item_name),
                        destination=data.get('destination')
                    )

                    return JSONResponse(
                        status_code=200,
                        content={
                            "status": "success",
                            "message": f"Item {item_name} processed successfully",
                            "details": {
                                "item_id": item_id,
                                "item_name": item_name,
                                "destination": data.get('destination'),
                                "files_moved": data.get('files_moved'),
                                "source": data.get('source', 'instagram')
                            }
                        }
                    )
                else:
                    error_message = result.get('error', f'Failed to process {item_name}')
                    log.error('[WebUI]: Item_id=%d error: %s', item_id, error_message)
                    self.database.update_raw_content_item_status(
                        item_id=item_id,
                        status='error',
                        error_message=error_message
                    )
                    return JSONResponse(
                        status_code=400,
                        content={
                            "status": "error",
                            "message": f"Failed to process item {item_name}",
                            "details": {
                                "item_id": item_id,
                                "item_name": item_name,
                                "error": error_message
                            }
                        }
                    )

            except Exception as e:
                log.error('[WebUI]: Exception while processing item_id=%d: %s', item_id, str(e), exc_info=True)
                try:
                    self.database.update_raw_content_item_status(
                        item_id=item_id,
                        status='error',
                        error_message=str(e)
                    )
                except Exception as ex:
                    log.debug('[WebUI]: Failed to update item status: %s', str(ex))
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "error",
                        "message": "Failed to process item",
                        "details": {
                            "error": str(e),
                            "exception_type": type(e).__name__
                        }
                    }
                )

        @self.app.post("/api/raw-content/process-selected")
        async def process_raw_content_selected(
            request: Request,
            user: dict = Depends(self.get_current_user)
        ):
            """
            Process multiple selected raw content items.
            Accepts list of item IDs and processes them in sequence/background.

            Expected JSON body:
            {
                "item_ids": [1, 2, 3, ...],  # Required: list of item IDs to process
                "run_async": true  # Optional: if true, process in background (default true)
            }

            Returns:
                JSON response with processing status and details.
            """
            if not self.content_processor:
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "error",
                        "message": "Raw content processing is not configured on this instance",
                        "details": None
                    }
                )

            user_id = str(user['id'])
            _, dest_dir_override = self._get_user_raw_processing_dirs(user_id)

            try:
                body = await request.json()
                item_ids = body.get('item_ids', [])
                run_async = body.get('run_async', True)
                dedupe_before_process = body.get('dedupe_before_process', True)

                if not isinstance(item_ids, list) or not item_ids:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "status": "error",
                            "message": "Missing or invalid item_ids list",
                            "details": None
                        }
                    )

                log.info('[WebUI]: Starting selected items processing for user %s: items=%s, async=%s',
                         user_id, item_ids, run_async)

                # Fetch selected items
                selected_items = self.database.get_raw_content_items_by_ids(user_id=user_id, item_ids=item_ids)

                if not selected_items:
                    return JSONResponse(
                        status_code=404,
                        content={
                            "status": "error",
                            "message": f"No items found for IDs: {item_ids}",
                            "details": None
                        }
                    )

                log.info('[WebUI]: Retrieved %d items for processing', len(selected_items))

                # Process in background if async, otherwise process sequentially
                if run_async:
                    async def process_selected_background():
                        try:
                            # Build candidates (parse content_files once) and mark them 'processing'.
                            candidates = []
                            for item in selected_items:
                                content_files_json = item.get('content_files', '[]')
                                content_files = []
                                if content_files_json:
                                    try:
                                        if isinstance(content_files_json, str):
                                            content_files = json.loads(content_files_json)
                                        else:
                                            content_files = content_files_json
                                    except (json.JSONDecodeError, ValueError):
                                        content_files = []
                                candidates.append({
                                    'id': item['id'],
                                    'item_name': item['item_name'],
                                    'item_path': item['item_path'],
                                    'mode': item['mode'],
                                    'content_files': content_files,
                                    'post_owner': item.get('post_owner'),
                                    'post_id': item.get('post_id'),
                                    'source': item.get('source')
                                })
                                self.database.update_raw_content_item_status(item_id=item['id'], status='processing')

                            # Process concurrently off the event loop; each item's status is written
                            # as soon as it finishes so the UI progress poll can follow it live.
                            processed_count, error_count = await self._process_raw_candidates_streaming(
                                user_id=user_id,
                                candidates=candidates,
                                dest_dir_override=dest_dir_override,
                                dedupe_before_process=dedupe_before_process
                            )

                            log.info('[WebUI]: Selected items processing complete - processed=%d, errors=%d',
                                     processed_count, error_count)
                        except Exception as e:
                            log.error('[WebUI]: Background processing failed: %s', str(e))

                    # Schedule background task
                    asyncio.create_task(process_selected_background())

                    return JSONResponse(
                        status_code=202,
                        content={
                            "status": "processing",
                            "message": f"Background processing started for {len(selected_items)} items",
                            "details": {
                                "items_count": len(selected_items),
                                "item_ids": item_ids
                            }
                        }
                    )

                else:
                    # Process synchronously - but still off the event loop. Calling
                    # process_candidate() directly here used to block the whole loop for the
                    # duration of the batch (minutes per post), so /selected-status could not be
                    # served and the UI had no way to show progress. The streaming helper runs the
                    # work in a worker thread and writes each item's status as it finishes, so the
                    # API stays responsive and the queue reflects progress while this request is
                    # still open.
                    candidates = []
                    for item in selected_items:
                        content_files_json = item.get('content_files', '[]')
                        content_files = []
                        if content_files_json:
                            try:
                                if isinstance(content_files_json, str):
                                    content_files = json.loads(content_files_json)
                                else:
                                    content_files = content_files_json
                            except (json.JSONDecodeError, ValueError):
                                content_files = []
                        candidates.append({
                            'id': item['id'],
                            'item_name': item['item_name'],
                            'item_path': item['item_path'],
                            'mode': item['mode'],
                            'content_files': content_files,
                            'post_owner': item.get('post_owner'),
                            'post_id': item.get('post_id'),
                            'source': item.get('source')
                        })
                        self.database.update_raw_content_item_status(item_id=item['id'], status='processing')

                    processed_count, error_count = await self._process_raw_candidates_streaming(
                        user_id=user_id,
                        candidates=candidates,
                        dest_dir_override=dest_dir_override,
                        dedupe_before_process=dedupe_before_process
                    )
                    errors = []

                    log.info('[WebUI]: Selected items processing complete (sync) - processed=%d, errors=%d',
                             processed_count, error_count)

                    return JSONResponse(
                        status_code=200 if error_count == 0 else 207,
                        content={
                            "status": "success" if error_count == 0 else "partial",
                            "message": f"Processed {processed_count} items, {error_count} errors",
                            "details": {
                                "processed_count": processed_count,
                                "error_count": error_count,
                                "errors": errors if errors else None
                            }
                        }
                    )

            except json.JSONDecodeError:
                return JSONResponse(
                    status_code=400,
                    content={
                        "status": "error",
                        "message": "Invalid JSON in request body",
                        "details": None
                    }
                )

        @self.app.post("/api/raw-content/selected-status")
        async def get_raw_content_selected_status(
            request: Request,
            user: dict = Depends(self.get_current_user)
        ):
            """
            Get current processing progress for selected queue item IDs.

            Expected JSON body:
            {
                "item_ids": [1, 2, 3]
            }
            """
            if not self.content_processor:
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "error",
                        "message": "Raw content processing is not configured on this instance",
                        "details": None
                    }
                )

            user_id = str(user['id'])

            try:
                body = await request.json()
                item_ids = body.get('item_ids', [])

                if not isinstance(item_ids, list) or not item_ids:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "status": "error",
                            "message": "Missing or invalid item_ids list",
                            "details": None
                        }
                    )

                selected_items = self.database.get_raw_content_items_by_ids(
                    user_id=user_id,
                    item_ids=[int(x) for x in item_ids]
                )

                completed_count = sum(1 for item in selected_items if item.get('status') == 'completed')
                error_count = sum(1 for item in selected_items if item.get('status') == 'error')
                processing_count = sum(1 for item in selected_items if item.get('status') == 'processing')
                scanned_count = sum(1 for item in selected_items if item.get('status') == 'scanned')

                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "success",
                        "details": {
                            "total": len(selected_items),
                            "completed": completed_count,
                            "error": error_count,
                            "processing": processing_count,
                            "scanned": scanned_count
                        }
                    }
                )
            except Exception as e:
                log.error('[WebUI]: Failed to get selected status for user %s: %s', user_id, str(e))
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "error",
                        "message": f"Failed to get selected status: {str(e)}",
                        "details": None
                    }
                )
            except Exception as e:
                log.error('[WebUI]: Failed to process selected items: %s', str(e), exc_info=True)
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "error",
                        "message": "Failed to process selected items",
                        "details": {
                            "error": str(e),
                            "exception_type": type(e).__name__
                        }
                    }
                )

        @self.app.post("/api/process-raw-content")
        async def process_raw_content(
            request: Request,
            dedupe_before_process: bool = True,
            user: dict = Depends(self.get_current_user)
        ):
            """
            Process raw content from WebDAV source directory.
            Organizes files into structured directories based on metadata.

            Returns:
                JSON response with processing result and statistics.
            """
            if not self.content_processor:
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "error",
                        "message": "Content processing is not configured on this instance",
                        "details": None
                    }
                )

            try:
                # Backward-compatible endpoint: run scan then process one batch.
                user_id = str(user['id'])
                source_dir_override, dest_dir_override = self._get_user_raw_processing_dirs(user_id)
                scan_id = str(uuid4())

                scan_kwargs = {
                    'limit': self.raw_scan_limit,
                    'offset': 0,
                    'user_id': user_id,
                    'database': self.database
                }
                if source_dir_override:
                    scan_kwargs['source_dir_override'] = source_dir_override
                if dest_dir_override:
                    scan_kwargs['dest_dir_override'] = dest_dir_override

                scan_result = self.content_processor.scan_source(**scan_kwargs)
                if scan_result.get('status') == 'error':
                    return JSONResponse(
                        status_code=400,
                        content={
                            "status": "error",
                            "message": "Scan failed",
                            "details": scan_result
                        }
                    )

                self.database.upsert_raw_content_scan_items(
                    user_id=user_id,
                    items=scan_result.get('processable_items', []),
                    scan_id=scan_id
                )

                # Process only one controlled batch to avoid blocking WebUI.
                batch_items = self.database.get_user_raw_content_items(
                    user_id=user_id,
                    status='scanned',
                    limit=self.raw_process_batch_size,
                    offset=0
                )

                processed_count = 0
                error_count = 0
                errors = []

                for item in batch_items:
                    content_files_json = item.get('content_files', '[]')
                    content_files = []
                    if content_files_json:
                        try:
                            if isinstance(content_files_json, str):
                                content_files = json.loads(content_files_json)
                            else:
                                content_files = content_files_json
                        except (json.JSONDecodeError, ValueError):
                            content_files = []

                    self.database.update_raw_content_item_status(item_id=item['id'], status='processing')
                    result = await asyncio.to_thread(
                        self.content_processor.process_candidate,
                        item_path=item['item_path'],
                        item_name=item['item_name'],
                        mode=item['mode'],
                        content_files=content_files,
                        post_owner=item.get('post_owner'),
                        post_id=item.get('post_id'),
                        source=item.get('source'),
                        dest_dir_override=dest_dir_override,
                        dedupe_before_process=dedupe_before_process
                    )

                    if result.get('status') == 'success':
                        data = result.get('data', {})
                        self.database.update_raw_content_item_status(
                            item_id=item['id'],
                            status='completed',
                            destination=data.get('destination'),
                            files_moved=data.get('files_moved'),
                            error_message=None
                        )
                        self.database.add_raw_item_to_processed(
                            user_id=user_id,
                            item_id=item['id'],
                            item_path=item['item_path'],
                            source=data.get('source', 'instagram'),
                            post_id=data.get('post_id', item['item_name']),
                            destination=data.get('destination')
                        )
                        processed_count += 1
                    else:
                        err = result.get('error', f"Failed to process {item['item_name']}")
                        self.database.update_raw_content_item_status(item_id=item['id'], status='error', error_message=err)
                        error_count += 1
                        errors.append(err)

                remaining_scanned = self.database._count(
                    table_name='raw_content_queue',
                    condition=f"user_id = '{user_id}' AND status = 'scanned'"
                )

                status = 'success' if error_count == 0 else ('partial' if processed_count > 0 else 'error')
                status_code = 200 if status == 'success' else (207 if status == 'partial' else 400)

                return JSONResponse(
                    status_code=status_code,
                    content={
                        "status": status,
                        "message": (
                            f"Batch complete: {processed_count} processed, {error_count} errors, "
                            f"{remaining_scanned} remaining"
                        ),
                        "details": {
                            "processed_count": processed_count,
                            "error_count": error_count,
                            "remaining_scanned": remaining_scanned,
                            "errors": errors[:10]
                        }
                    }
                )

            except Exception as e:
                error_msg = f"Content processing failed: {str(e)}"
                log.error('[WebUI]: %s', error_msg)
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "error",
                        "message": error_msg,
                        "details": None
                    }
                )

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
