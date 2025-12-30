"""
This module provides a FastAPI-based web UI for the Pyinstabot-Downloader bot.
It displays queue/processed messages, user statistics, and accepts new link submissions.
Authentication is handled via Telegram Login Widget.
"""
import os
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
        GET /dashboard: User dashboard with counters and recent messages.
        GET /api/queue: Paginated queue messages for current user.
        GET /api/processed: Paginated processed messages for current user.
        POST /api/submit: Submit a new Instagram link to the queue.
        GET /logout: Clear session and redirect to home.

    Examples:
        >>> from modules.database import DatabaseClient
        >>> from vault import VaultClient
        >>> vault = VaultClient()
        >>> database = DatabaseClient(vault=vault, db_role='pyinstabot-downloader')
        >>> webui = WebUI(
        ...     database=database,
        ...     bot_token='123456:ABC-DEF',
        ...     session_secret='my-secret-key',
        ...     port=8080
        ... )
        >>> # Run in separate thread or process
        >>> import threading
        >>> thread = threading.Thread(target=webui.run, daemon=True)
        >>> thread.start()
    """

    def __init__(
        self,
        database: object = None,
        vault: object = None,
        bot_token: str = None,
        bot_username: str = None,
        session_secret: str = None,
        host: str = '0.0.0.0',
        port: int = None,
        templates_dir: str = 'src/templates',
        version: str = '0.0.0'
    ):
        """
        Initialize the WebUI instance.

        Args:
            database (DatabaseClient): Database client instance for accessing data.
            vault (object): Vault client instance for accessing secrets.
            bot_token (str): Telegram bot token for verifying authentication.
            bot_username (str): Telegram bot username for Login Widget.
            session_secret (str): Secret key for session cookies (generate random if None).
            host (str): Host to bind the web server (default '0.0.0.0').
            port (int): Port to bind the web server (default from constants).
            templates_dir (str): Directory containing Jinja2 templates.
            version (str): Application version string.
        """
        if not database:
            raise ValueError("Database client is required for WebUI")
        # Resolve sensitive configuration: prefer arguments, fallback to Vault kv2
        self.database = database

        self.vault = vault

        if bot_token:
            self.bot_token = bot_token
        else:
            try:
                self.bot_token = self.vault.kv2engine.read_secret(path='configuration/telegram').get('token', None)
            except ValueError as error:
                log.warning('[WebUI]: Failed to read Telegram token from Vault: %s', str(error))

        if not self.bot_token:
            raise ValueError("Telegram bot token is required (provide via argument or Vault kv2: configuration/telegram)")

        # Resolve bot username for Telegram Login Widget
        self.bot_username = bot_username
        if not self.bot_username:
            if self.vault:
                try:
                    self.bot_username = self.vault.kv2engine.read_secret(path='configuration/telegram').get('username', None)
                # pylint: disable=broad-except
                except Exception as error:
                    log.warning('[WebUI]: Failed to read Telegram username from Vault: %s', str(error))
            if not self.bot_username:
                log.error('[WebUI]: Telegram bot username is not set (provide via argument or Vault kv2: configuration/telegram)')

        # Resolve session secret: prefer arguments, fallback to Vault kv2, then generate random
        if session_secret:
            self.session_secret = session_secret
        else:
            self.session_secret = None
            if self.vault:
                webui_secret = self.vault.kv2engine.read_secret(path='configuration/webui')
                if webui_secret:
                    self.session_secret = webui_secret.get('session-secret', None)
                else:
                    self.session_secret = os.urandom(32).hex()

        # Host and port configuration
        self.host = host
        self.port = port

        # Initialize FastAPI app
        self.app = FastAPI(title="Instagram Downloader WebUI", version=version)
        self.app.add_middleware(SessionMiddleware, secret_key=self.session_secret)

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
            return self.templates.TemplateResponse("login.html", {"request": request, "bot_username": self.bot_username})

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
            Submit a new Instagram link to the queue.

            Form data:
                url (str): Instagram post/profile URL
            """
            import re
            from modules.tools import get_hash
            from configs.constants import REGEX_SPECIFIC_LINK, REGEX_PROFILE_LINK

            user_id = str(user['id'])

            # Validate URL format
            if re.match(REGEX_SPECIFIC_LINK, url):
                link_type = 'post'
                post_id = get_hash(url)
            elif re.match(REGEX_PROFILE_LINK, url):
                link_type = 'profile'
                post_id = get_hash(url)
            else:
                raise HTTPException(status_code=400, detail="Invalid Instagram URL")

            # Check uniqueness
            if not self.database.check_message_uniqueness(post_id=post_id, user_id=user_id):
                raise HTTPException(status_code=409, detail="This link is already in your queue or processed")

            # Add to queue
            scheduled_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            data = {
                'user_id': user_id,
                'post_id': post_id,
                'post_url': url,
                'post_owner': None,  # Will be filled by downloader
                'link_type': link_type,
                'message_id': f"web_{post_id}",
                'chat_id': user_id,
                'scheduled_time': scheduled_time,
                'download_status': 'not started',
                'upload_status': 'not started'
            }

            result = self.database.add_message_to_queue(data=data)
            log.info('[WebUI]: User %s submitted link: %s (%s)', user_id, url, post_id)

            return JSONResponse({
                'status': 'success',
                'message': 'Link added to queue',
                'post_id': post_id
            })

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
        import uvicorn
        log.info('[WebUI]: Starting web server on %s:%s', self.host, self.port)
        uvicorn.run(self.app, host=self.host, port=self.port, log_level="info")
