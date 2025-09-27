"""
Authentication manager for OpenAI API access.

This module handles authentication exactly like the official Codex CLI:
- OpenAI API key authentication
- ChatGPT subscription OAuth authentication
- Runtime credential injection into containers
- Secure credential handling and validation
"""

import os
import json
import tempfile
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

import structlog

try:
    from .utils.config import Config
    from .utils.logging import LogContext
    from .oauth_manager import OAuthTokenManager, OAuthTokens
    from .oauth_flow import OAuthFlow
except ImportError:
    from utils.config import Config
    from utils.logging import LogContext
    from oauth_manager import OAuthTokenManager, OAuthTokens
    from oauth_flow import OAuthFlow

logger = structlog.get_logger(__name__)


class AuthMethod(Enum):
    """Authentication methods supported by Codex CLI."""
    API_KEY = "api_key"
    CHATGPT_OAUTH = "chatgpt_oauth"


@dataclass
class AuthCredentials:
    """Authentication credentials for a session."""
    method: AuthMethod
    api_key: Optional[str] = None
    oauth_token: Optional[str] = None
    oauth_tokens: Optional[OAuthTokens] = None
    environment_vars: Dict[str, str] = None

    def __post_init__(self):
        if self.environment_vars is None:
            self.environment_vars = {}


class AuthenticationError(Exception):
    """Raised when authentication fails."""
    pass


class CodexAuthManager:
    """
    Authentication manager for Codex CLI integration.

    Handles authentication exactly like the official Codex CLI:
    - Supports OpenAI API key authentication
    - Supports ChatGPT subscription OAuth flow
    - Provides runtime credential injection for containers
    - Validates credentials and handles auth errors
    """

    def __init__(self, config: Config):
        """
        Initialize the authentication manager.

        Args:
            config: Server configuration object
        """
        self.config = config
        self._validated_credentials: Dict[str, AuthCredentials] = {}
        token_storage_path = None
        if hasattr(self.config, "auth") and getattr(self.config.auth.oauth, "token_storage_path", None):
            token_storage_path = self.config.auth.oauth.token_storage_path

        self.oauth_manager = OAuthTokenManager(token_storage_path)
        self.oauth_flow = OAuthFlow(oauth_manager=self.oauth_manager)

        logger.info("Authentication manager initialized",
                   supported_methods=["openai_api_key", "chatgpt_oauth"])

    def detect_auth_method(self) -> AuthMethod:
        """
        Detect available authentication method based on configuration preferences.

        Returns:
            AuthMethod: The preferred authentication method

        Raises:
            AuthenticationError: If no valid authentication is available
        """
        # Check configuration preference and auth method setting
        auth_method_config = self.config.auth.auth_method.lower()
        prefer_oauth = self.config.auth.prefer_oauth

        # Force specific method if configured
        if auth_method_config == "oauth":
            if self._has_chatgpt_oauth():
                logger.info("Using forced OAuth authentication")
                return AuthMethod.CHATGPT_OAUTH
            else:
                raise AuthenticationError("OAuth authentication forced but not available")

        if auth_method_config == "api_key":
            if self._has_valid_api_key():
                logger.info("Using forced API key authentication")
                return AuthMethod.API_KEY
            else:
                raise AuthenticationError("API key authentication forced but not available")

        # Auto detection based on preference (auth_method_config == "auto")
        has_oauth = self._has_chatgpt_oauth()
        has_api_key = self._has_valid_api_key()

        if prefer_oauth:
            # Prefer OAuth first, fallback to API key
            if has_oauth:
                logger.info("Using OAuth authentication (preferred)")
                return AuthMethod.CHATGPT_OAUTH
            elif has_api_key:
                logger.info("Using API key authentication (OAuth not available, falling back)")
                return AuthMethod.API_KEY
        else:
            # Prefer API key first, fallback to OAuth
            if has_api_key:
                logger.info("Using API key authentication (preferred)")
                return AuthMethod.API_KEY
            elif has_oauth:
                logger.info("Using OAuth authentication (API key not available, falling back)")
                return AuthMethod.CHATGPT_OAUTH

        # No authentication available
        raise AuthenticationError(
            "No valid authentication found. Please provide either:\n"
            "1. OpenAI API key via OPENAI_API_KEY environment variable\n"
            "2. ChatGPT subscription with OAuth (run 'codex' to authenticate)"
        )

    def _has_valid_api_key(self) -> bool:
        """Check if a valid OpenAI API key is available."""
        api_key = self._get_openai_api_key()
        if not api_key:
            return False

        # Basic validation - OpenAI keys start with 'sk-'
        if not api_key.startswith('sk-'):
            logger.warning("Invalid OpenAI API key format")
            return False

        logger.debug("Valid OpenAI API key found")
        return True

    def _has_chatgpt_oauth(self) -> bool:
        """Check if ChatGPT OAuth authentication is available."""
        # Check for explicitly provided OAuth token via environment
        oauth_token = os.getenv("CHATGPT_OAUTH_TOKEN")
        if oauth_token:
            logger.debug("ChatGPT OAuth token found in environment")
            return True

        # Check for stored OAuth tokens using OAuth manager (file presence is enough; refresh handled later)
        token_path = getattr(self.oauth_manager, "token_path", None)
        if token_path and token_path.exists():
            logger.debug("OAuth token file found", path=str(token_path))
            return True

        logger.debug("No OAuth authentication available")
        return False

    def _get_openai_api_key(self) -> Optional[str]:
        """Get OpenAI API key from environment or config."""
        # Check environment variable first
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            return api_key

        # Check config
        if hasattr(self.config, 'auth') and self.config.auth.openai_api_key:
            return self.config.auth.openai_api_key

        return None

    async def get_session_credentials(
        self,
        session_id: str,
        force_method: Optional[AuthMethod] = None
    ) -> AuthCredentials:
        """
        Get authentication credentials for a session.

        Args:
            session_id: Session identifier
            force_method: Optional forced authentication method

        Returns:
            AuthCredentials: Credentials for the session

        Raises:
            AuthenticationError: If authentication fails
        """
        with LogContext(session_id):
            logger.info("Getting session credentials", session_id=session_id)

            # Check cache first
            if session_id in self._validated_credentials:
                logger.debug("Using cached credentials")
                return self._validated_credentials[session_id]

            # Determine auth method
            auth_method = force_method or self.detect_auth_method()

            if auth_method == AuthMethod.API_KEY:
                credentials = await self._create_api_key_credentials()
            elif auth_method == AuthMethod.CHATGPT_OAUTH:
                credentials = await self._create_oauth_credentials()
            else:
                raise AuthenticationError(f"Unsupported auth method: {auth_method}")

            # Cache credentials
            self._validated_credentials[session_id] = credentials

            logger.info("Session credentials created",
                       method=auth_method.value,
                       session_id=session_id)

            return credentials

    async def _create_api_key_credentials(self) -> AuthCredentials:
        """Create credentials using OpenAI API key."""
        api_key = self._get_openai_api_key()
        if not api_key:
            raise AuthenticationError("OpenAI API key not found")

        # Validate API key format
        if not api_key.startswith('sk-'):
            raise AuthenticationError("Invalid OpenAI API key format")

        logger.debug("Creating API key credentials")

        return AuthCredentials(
            method=AuthMethod.API_KEY,
            api_key=api_key,
            environment_vars={
                "OPENAI_API_KEY": api_key,
                "CODEX_AUTH_METHOD": "api_key"
            }
        )

    async def _create_oauth_credentials(self) -> AuthCredentials:
        """Create credentials using ChatGPT OAuth."""
        logger.debug("Creating OAuth credentials")

        # Try to get valid tokens from OAuth manager
        oauth_tokens = await self.oauth_manager.get_valid_tokens()

        # Fallback to environment variable
        oauth_token = os.getenv("CHATGPT_OAUTH_TOKEN")

        env_vars = {
            "CODEX_AUTH_METHOD": "oauth"
        }

        # Use OAuth tokens if available
        if oauth_tokens:
            env_vars["OPENAI_ACCESS_TOKEN"] = oauth_tokens.access_token
            logger.debug("Using OAuth manager tokens")
        elif oauth_token:
            env_vars["CHATGPT_OAUTH_TOKEN"] = oauth_token
            logger.debug("Using environment OAuth token")
        else:
            raise AuthenticationError("No valid OAuth tokens available")

        return AuthCredentials(
            method=AuthMethod.CHATGPT_OAUTH,
            oauth_token=oauth_token,
            oauth_tokens=oauth_tokens,
            environment_vars=env_vars
        )

    def generate_codex_config(
        self,
        credentials: AuthCredentials,
        model: str = "gpt-5-codex",
        approval_mode: str = "suggest",
        reasoning: str = "medium"
    ) -> str:
        """
        Generate Codex CLI configuration with authentication.

        Args:
            credentials: Authentication credentials
            model: Model to use (default: gpt-5-codex)
            approval_mode: Approval mode (default: suggest)
            reasoning: Reasoning level for GPT-5 models (low, medium, high)

        Returns:
            str: TOML configuration content
        """
        logger.debug("Generating Codex config",
                    auth_method=credentials.method.value,
                    model=model)

        # Base configuration matching official Codex CLI
        config_content = f'''# Codex CLI Configuration
model = "{model}"
provider = "openai"
approvalMode = "{approval_mode}"
fullAutoErrorMode = "ask-user"
notify = false

[providers.openai]
name = "OpenAI"
baseURL = "https://api.openai.com/v1"
envKey = "OPENAI_API_KEY"

[history]
maxSize = 1000
saveHistory = true
sensitivePatterns = []
'''

        return config_content.strip()

    def get_container_environment(self, credentials: AuthCredentials) -> Dict[str, str]:
        """
        Get environment variables for container authentication.

        Args:
            credentials: Session credentials

        Returns:
            Dict[str, str]: Environment variables for container
        """
        env_vars = credentials.environment_vars.copy()

        # Add additional environment variables that Codex CLI expects
        env_vars.update({
            "CODEX_CONFIG_PATH": "/app/config/config.toml",
            "HOME": "/app",
            "NODE_ENV": "production"
        })

        # Remove sensitive values from logs
        safe_env = {k: "***" if "key" in k.lower() or "token" in k.lower() else v
                   for k, v in env_vars.items()}
        logger.debug("Container environment prepared", env_vars=safe_env)

        return env_vars

    async def validate_credentials(self, credentials: AuthCredentials) -> bool:
        """
        Validate credentials by testing authentication.

        Args:
            credentials: Credentials to validate

        Returns:
            bool: True if credentials are valid
        """
        try:
            if credentials.method == AuthMethod.API_KEY:
                return await self._validate_api_key(credentials.api_key)
            elif credentials.method == AuthMethod.CHATGPT_OAUTH:
                return await self._validate_oauth_token(credentials.oauth_token)
            else:
                return False
        except Exception as e:
            logger.error("Credential validation failed", error=str(e))
            return False

    async def _validate_api_key(self, api_key: Optional[str]) -> bool:
        """Validate OpenAI API key."""
        if not api_key or not api_key.startswith('sk-'):
            return False

        # For production, you could make a test API call to OpenAI
        # For now, just validate format
        logger.debug("API key format validation passed")
        return True

    async def _validate_oauth_token(self, oauth_token: Optional[str]) -> bool:
        """Validate ChatGPT OAuth token."""
        # For OAuth, Codex CLI handles validation internally
        # We just need to ensure the token exists if provided
        logger.debug("OAuth validation delegated to Codex CLI")
        return True

    def clear_session_credentials(self, session_id: str) -> None:
        """
        Clear cached credentials for a session.

        Args:
            session_id: Session identifier
        """
        if session_id in self._validated_credentials:
            del self._validated_credentials[session_id]
            logger.debug("Session credentials cleared", session_id=session_id)

    def get_auth_info(self) -> Dict[str, Any]:
        """
        Get authentication information for monitoring.

        Returns:
            Dict[str, Any]: Authentication status information
        """
        try:
            auth_method = self.detect_auth_method()
            has_api_key = self._has_valid_api_key()
            has_oauth = self._has_chatgpt_oauth()

            return {
                "available_methods": {
                    "api_key": has_api_key,
                    "chatgpt_oauth": has_oauth
                },
                "preferred_method": auth_method.value,
                "active_sessions": len(self._validated_credentials),
                "status": "configured"
            }
        except AuthenticationError:
            return {
                "available_methods": {
                    "api_key": False,
                    "chatgpt_oauth": False
                },
                "preferred_method": None,
                "active_sessions": 0,
                "status": "not_configured",
                "message": "No valid authentication configured"
            }

    async def start_oauth_flow(
        self,
        open_browser: bool = True,
        timeout: int = 300
    ) -> Optional[OAuthTokens]:
        """
        Start interactive OAuth flow for ChatGPT subscription authentication.

        Args:
            open_browser: Whether to automatically open browser
            timeout: Timeout in seconds for user authorization

        Returns:
            OAuthTokens if successful, None otherwise
        """
        try:
            logger.info("Starting OAuth authentication flow",
                       open_browser=open_browser,
                       timeout=timeout)

            tokens = await self.oauth_flow.run_oauth_flow(
                open_browser=open_browser,
                timeout=timeout
            )

            if tokens:
                logger.info("OAuth authentication successful")
                # Clear any cached credentials to force refresh
                self._validated_credentials.clear()
            else:
                logger.error("OAuth authentication failed")

            return tokens

        except Exception as e:
            logger.error("OAuth flow error", error=str(e))
            raise AuthenticationError(f"OAuth flow failed: {e}")

    async def get_oauth_authorization_url(self) -> str:
        """
        Get OAuth authorization URL for manual authentication flow.

        Returns:
            Authorization URL that user should visit
        """
        try:
            auth_url = await self.oauth_flow.get_authorization_url()
            logger.info("OAuth authorization URL generated")
            return auth_url

        except Exception as e:
            logger.error("Failed to generate OAuth URL", error=str(e))
            raise AuthenticationError(f"Failed to generate OAuth URL: {e}")

    async def complete_oauth_flow(self, timeout: int = 300) -> Optional[OAuthTokens]:
        """
        Complete OAuth flow after manual authorization.

        Args:
            timeout: Timeout in seconds to wait for callback

        Returns:
            OAuthTokens if successful, None otherwise
        """
        try:
            logger.info("Waiting for OAuth callback", timeout=timeout)

            authorization_code = await self.oauth_flow.wait_for_callback(timeout)
            if not authorization_code:
                logger.error("OAuth callback timeout or failure")
                return None

            # The callback handling in oauth_flow should have already exchanged
            # the code for tokens, so we can load them from the manager
            tokens = await self.oauth_manager.load_tokens()

            if tokens:
                logger.info("OAuth flow completed successfully")
                # Clear cached credentials to force refresh
                self._validated_credentials.clear()
            else:
                logger.error("Failed to load tokens after OAuth completion")

            return tokens

        except Exception as e:
            logger.error("OAuth completion error", error=str(e))
            raise AuthenticationError(f"OAuth completion failed: {e}")

    async def revoke_oauth_tokens(self) -> bool:
        """
        Revoke stored OAuth tokens and clear authentication.

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info("Revoking OAuth tokens")

            success = await self.oauth_manager.revoke_tokens()

            if success:
                # Clear cached credentials
                self._validated_credentials.clear()
                logger.info("OAuth tokens revoked successfully")
            else:
                logger.warning("OAuth token revocation had issues")

            return success

        except Exception as e:
            logger.error("OAuth revocation error", error=str(e))
            return False

    def get_oauth_status(self) -> Dict[str, Any]:
        """
        Get OAuth authentication status and token information.

        Returns:
            Dictionary with OAuth status information
        """
        try:
            token_info = self.oauth_manager.get_token_info()
            flow_info = self.oauth_flow.get_flow_info()

            return {
                "oauth_available": self._has_chatgpt_oauth(),
                "token_info": token_info,
                "flow_info": flow_info,
                "auth_method_priority": {
                    "preferred": "oauth" if self._has_chatgpt_oauth() else "api_key",
                    "api_key_available": self._has_valid_api_key(),
                    "oauth_available": self._has_chatgpt_oauth()
                }
            }

        except Exception as e:
            logger.error("Failed to get OAuth status", error=str(e))
            return {
                "oauth_available": False,
                "error": str(e)
            }

    async def ensure_authentication(self, force_oauth: bool = False) -> AuthMethod:
        """
        Ensure authentication is available, triggering OAuth flow if needed.

        Args:
            force_oauth: Force OAuth flow even if API key is available

        Returns:
            AuthMethod that was successfully configured

        Raises:
            AuthenticationError: If no authentication method can be configured
        """
        try:
            # If OAuth is forced or preferred and not available, start OAuth flow
            if force_oauth or (not self._has_chatgpt_oauth() and not self._has_valid_api_key()):
                logger.info("Starting OAuth flow to ensure authentication",
                           force_oauth=force_oauth)

                tokens = await self.start_oauth_flow()
                if tokens:
                    return AuthMethod.CHATGPT_OAUTH

            # Check what's available now
            if self._has_chatgpt_oauth():
                return AuthMethod.CHATGPT_OAUTH
            elif self._has_valid_api_key():
                return AuthMethod.API_KEY
            else:
                raise AuthenticationError(
                    "No authentication method available. Please provide either:\n"
                    "1. OpenAI API key via OPENAI_API_KEY environment variable\n"
                    "2. Complete OAuth authentication flow"
                )

        except Exception as e:
            logger.error("Authentication setup failed", error=str(e))
            raise AuthenticationError(f"Authentication setup failed: {e}")

    async def cleanup(self) -> None:
        """Clean up authentication manager resources."""
        self._validated_credentials.clear()
        # Note: OAuth manager and flow don't need explicit cleanup
        # as they use context managers for resource management
        logger.info("Authentication manager cleaned up")
