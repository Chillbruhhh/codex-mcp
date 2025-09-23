"""
OAuth flow handler for interactive ChatGPT subscription authentication.

This module implements the complete OAuth2 authorization code flow with PKCE
for ChatGPT subscription authentication, including browser integration and
local callback server handling.
"""

import asyncio
import secrets
import hashlib
import base64
import webbrowser
import urllib.parse
from typing import Optional, Tuple, Dict, Any
from datetime import datetime
import aiohttp
from aiohttp import web
import structlog

try:
    from .oauth_manager import OAuthTokenManager, OAuthTokens
except ImportError:
    from oauth_manager import OAuthTokenManager, OAuthTokens

logger = structlog.get_logger(__name__)


class OAuthFlowError(Exception):
    """OAuth flow specific errors."""
    pass


class OAuthFlow:
    """
    Handles interactive OAuth2 authorization code flow for ChatGPT authentication.

    Implements the complete flow including:
    - PKCE (Proof Key for Code Exchange) for security
    - Local HTTP server for OAuth callback handling
    - Browser integration for user authorization
    - State parameter for CSRF protection
    """

    def __init__(
        self,
        client_id: str = "codex-cli",
        oauth_manager: Optional[OAuthTokenManager] = None,
        callback_port: int = 8765
    ):
        """
        Initialize OAuth flow handler.

        Args:
            client_id: OAuth client identifier
            oauth_manager: Token manager instance
            callback_port: Local port for OAuth callback server
        """
        self.client_id = client_id
        self.callback_port = callback_port
        self.oauth_manager = oauth_manager or OAuthTokenManager()

        # OAuth endpoints - would need actual OpenAI OAuth endpoints
        self.auth_base_url = "https://auth.openai.com"
        self.authorization_endpoint = f"{self.auth_base_url}/oauth/authorize"
        self.token_endpoint = f"{self.auth_base_url}/oauth/token"

        # Flow state
        self._server: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._callback_future: Optional[asyncio.Future] = None
        self._flow_state = {
            "code_verifier": None,
            "state": None,
            "redirect_uri": None
        }

        logger.info("OAuth flow handler initialized",
                   client_id=client_id,
                   callback_port=callback_port)

    def _generate_pkce_pair(self) -> Tuple[str, str]:
        """
        Generate PKCE code verifier and challenge.

        Returns:
            Tuple of (code_verifier, code_challenge)
        """
        # Generate cryptographically secure random code verifier
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8')
        code_verifier = code_verifier.rstrip('=')  # Remove padding

        # Create code challenge using SHA256
        code_challenge = hashlib.sha256(code_verifier.encode('utf-8')).digest()
        code_challenge = base64.urlsafe_b64encode(code_challenge).decode('utf-8')
        code_challenge = code_challenge.rstrip('=')  # Remove padding

        return code_verifier, code_challenge

    def _generate_state(self) -> str:
        """Generate secure state parameter for CSRF protection."""
        return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')

    async def start_callback_server(self) -> str:
        """
        Start local HTTP server for OAuth callback handling.

        Returns:
            The redirect URI for the OAuth flow
        """
        self._server = web.Application()
        self._server.router.add_get('/callback', self._handle_callback)
        self._server.router.add_get('/success', self._handle_success)
        self._server.router.add_get('/error', self._handle_error)

        self._runner = web.AppRunner(self._server)
        await self._runner.setup()

        # Try to bind to the specified port, with fallback
        port = self.callback_port
        max_attempts = 10

        for attempt in range(max_attempts):
            try:
                self._site = web.TCPSite(self._runner, 'localhost', port)
                await self._site.start()

                redirect_uri = f"http://localhost:{port}/callback"
                self._flow_state["redirect_uri"] = redirect_uri

                logger.info("OAuth callback server started",
                           port=port,
                           redirect_uri=redirect_uri)
                return redirect_uri

            except OSError as e:
                if attempt < max_attempts - 1:
                    port += 1
                    logger.debug("Port unavailable, trying next",
                               attempted_port=port - 1,
                               next_port=port)
                else:
                    raise OAuthFlowError(f"Could not bind callback server after {max_attempts} attempts: {e}")

    async def stop_callback_server(self) -> None:
        """Stop the OAuth callback server."""
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()

        logger.debug("OAuth callback server stopped")

    async def _handle_callback(self, request: web.Request) -> web.Response:
        """Handle OAuth authorization callback."""
        try:
            # Extract parameters from callback
            code = request.query.get('code')
            state = request.query.get('state')
            error = request.query.get('error')
            error_description = request.query.get('error_description')

            logger.info("OAuth callback received",
                       has_code=code is not None,
                       has_state=state is not None,
                       has_error=error is not None)

            if error:
                error_msg = f"OAuth error: {error}"
                if error_description:
                    error_msg += f" - {error_description}"

                logger.error("OAuth authorization failed", error=error_msg)

                if self._callback_future and not self._callback_future.done():
                    self._callback_future.set_exception(OAuthFlowError(error_msg))

                return web.Response(
                    text=self._generate_error_page(error_msg),
                    content_type='text/html'
                )

            # Validate state parameter
            if state != self._flow_state.get("state"):
                error_msg = "Invalid state parameter - possible CSRF attack"
                logger.error("OAuth state validation failed")

                if self._callback_future and not self._callback_future.done():
                    self._callback_future.set_exception(OAuthFlowError(error_msg))

                return web.Response(
                    text=self._generate_error_page(error_msg),
                    content_type='text/html'
                )

            if not code:
                error_msg = "No authorization code received"
                logger.error("OAuth callback missing authorization code")

                if self._callback_future and not self._callback_future.done():
                    self._callback_future.set_exception(OAuthFlowError(error_msg))

                return web.Response(
                    text=self._generate_error_page(error_msg),
                    content_type='text/html'
                )

            # Success - complete the future with the authorization code
            if self._callback_future and not self._callback_future.done():
                self._callback_future.set_result(code)

            # Redirect to success page
            return web.Response(
                status=302,
                headers={'Location': '/success'}
            )

        except Exception as e:
            logger.error("OAuth callback handling failed", error=str(e))

            if self._callback_future and not self._callback_future.done():
                self._callback_future.set_exception(e)

            return web.Response(
                text=self._generate_error_page(f"Callback handling failed: {e}"),
                content_type='text/html'
            )

    async def _handle_success(self, request: web.Request) -> web.Response:
        """Handle successful OAuth completion."""
        return web.Response(
            text=self._generate_success_page(),
            content_type='text/html'
        )

    async def _handle_error(self, request: web.Request) -> web.Response:
        """Handle OAuth error page."""
        error_msg = request.query.get('error', 'Unknown error occurred')
        return web.Response(
            text=self._generate_error_page(error_msg),
            content_type='text/html'
        )

    def _generate_success_page(self) -> str:
        """Generate HTML success page."""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authentication Successful</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; text-align: center; }
                .success { color: #28a745; font-size: 24px; margin-bottom: 20px; }
                .message { font-size: 16px; color: #333; }
                .logo { width: 64px; height: 64px; margin: 20px auto; }
            </style>
        </head>
        <body>
            <div class="logo">🤖</div>
            <div class="success">✅ Authentication Successful!</div>
            <div class="message">
                <p>Your ChatGPT subscription has been successfully linked to Codex CLI MCP Server.</p>
                <p>You can now close this window and return to your terminal.</p>
                <p>The server will use your ChatGPT subscription quota for all requests.</p>
            </div>
        </body>
        </html>
        """

    def _generate_error_page(self, error_message: str) -> str:
        """Generate HTML error page."""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authentication Error</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; text-align: center; }}
                .error {{ color: #dc3545; font-size: 24px; margin-bottom: 20px; }}
                .message {{ font-size: 16px; color: #333; }}
                .details {{ background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px; }}
                .logo {{ width: 64px; height: 64px; margin: 20px auto; }}
            </style>
        </head>
        <body>
            <div class="logo">🤖</div>
            <div class="error">❌ Authentication Failed</div>
            <div class="message">
                <p>There was an error during the authentication process.</p>
                <div class="details">
                    <strong>Error:</strong> {error_message}
                </div>
                <p>Please close this window and try again from your terminal.</p>
                <p>If the problem persists, you can use an OpenAI API key instead.</p>
            </div>
        </body>
        </html>
        """

    def build_authorization_url(
        self,
        scope: str = "openai-api",
        additional_params: Optional[Dict[str, str]] = None
    ) -> Tuple[str, str, str]:
        """
        Build OAuth authorization URL with PKCE parameters.

        Args:
            scope: OAuth scope to request
            additional_params: Additional query parameters

        Returns:
            Tuple of (authorization_url, code_verifier, state)
        """
        # Generate PKCE parameters
        code_verifier, code_challenge = self._generate_pkce_pair()
        state = self._generate_state()

        # Store in flow state
        self._flow_state.update({
            "code_verifier": code_verifier,
            "state": state
        })

        # Build authorization URL parameters
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self._flow_state["redirect_uri"],
            "scope": scope,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "prompt": "consent"  # Force user consent screen
        }

        # Add any additional parameters
        if additional_params:
            params.update(additional_params)

        # Build URL
        authorization_url = f"{self.authorization_endpoint}?" + urllib.parse.urlencode(params)

        logger.info("Authorization URL built",
                   url_length=len(authorization_url),
                   scope=scope)

        return authorization_url, code_verifier, state

    async def run_oauth_flow(
        self,
        scope: str = "openai-api",
        timeout: int = 300,
        open_browser: bool = True
    ) -> Optional[OAuthTokens]:
        """
        Run complete OAuth authorization flow.

        Args:
            scope: OAuth scope to request
            timeout: Timeout in seconds for user authorization
            open_browser: Whether to automatically open browser

        Returns:
            OAuthTokens if successful, None otherwise
        """
        try:
            logger.info("Starting OAuth authorization flow",
                       scope=scope,
                       timeout=timeout,
                       open_browser=open_browser)

            # Start callback server
            redirect_uri = await self.start_callback_server()

            # Build authorization URL
            auth_url, code_verifier, state = self.build_authorization_url(scope)

            # Create future for callback handling
            self._callback_future = asyncio.Future()

            # Open browser if requested
            if open_browser:
                logger.info("Opening browser for user authorization")
                webbrowser.open(auth_url)
            else:
                logger.info("Manual authorization required",
                           authorization_url=auth_url)

            # Wait for authorization code with timeout
            try:
                authorization_code = await asyncio.wait_for(
                    self._callback_future,
                    timeout=timeout
                )
                logger.info("Authorization code received")

            except asyncio.TimeoutError:
                logger.error("OAuth flow timed out", timeout=timeout)
                return None

            # Exchange authorization code for tokens
            async with OAuthTokenManager() as token_manager:
                tokens = await token_manager.store_tokens_from_code(
                    authorization_code=authorization_code,
                    code_verifier=code_verifier,
                    redirect_uri=redirect_uri
                )

                if tokens:
                    logger.info("OAuth flow completed successfully")
                    return tokens
                else:
                    logger.error("Token exchange failed")
                    return None

        except Exception as e:
            logger.error("OAuth flow failed", error=str(e))
            return None

        finally:
            # Always clean up callback server
            try:
                await self.stop_callback_server()
            except Exception as e:
                logger.warning("Error stopping callback server", error=str(e))

    async def get_authorization_url(self, scope: str = "openai-api") -> str:
        """
        Get authorization URL for manual OAuth flow.

        Args:
            scope: OAuth scope to request

        Returns:
            Authorization URL for manual completion
        """
        # Start callback server
        await self.start_callback_server()

        # Build and return authorization URL
        auth_url, _, _ = self.build_authorization_url(scope)
        return auth_url

    async def wait_for_callback(self, timeout: int = 300) -> Optional[str]:
        """
        Wait for OAuth callback after manual authorization.

        Args:
            timeout: Timeout in seconds

        Returns:
            Authorization code if received, None on timeout
        """
        self._callback_future = asyncio.Future()

        try:
            authorization_code = await asyncio.wait_for(
                self._callback_future,
                timeout=timeout
            )
            return authorization_code

        except asyncio.TimeoutError:
            logger.error("Callback wait timed out", timeout=timeout)
            return None

        finally:
            await self.stop_callback_server()

    def get_flow_info(self) -> Dict[str, Any]:
        """
        Get information about current OAuth flow state.

        Returns:
            Dictionary with flow information
        """
        return {
            "client_id": self.client_id,
            "callback_port": self.callback_port,
            "redirect_uri": self._flow_state.get("redirect_uri"),
            "server_running": self._site is not None,
            "awaiting_callback": self._callback_future is not None and not self._callback_future.done(),
            "authorization_endpoint": self.authorization_endpoint,
            "token_endpoint": self.token_endpoint
        }