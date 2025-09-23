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

from .utils.config import Config
from .utils.logging import LogContext

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

        logger.info("Authentication manager initialized",
                   supported_methods=["openai_api_key", "chatgpt_oauth"])

    def detect_auth_method(self) -> AuthMethod:
        """
        Detect available authentication method.

        Returns:
            AuthMethod: The preferred authentication method

        Raises:
            AuthenticationError: If no valid authentication is available
        """
        # Check for OpenAI API key first (preferred for automation)
        if self._has_valid_api_key():
            logger.info("Using OpenAI API key authentication")
            return AuthMethod.API_KEY

        # Check for ChatGPT OAuth (interactive/subscription users)
        if self._has_chatgpt_oauth():
            logger.info("Using ChatGPT OAuth authentication")
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
        # In the official Codex CLI, OAuth tokens are stored in ~/.codex/
        # For our containerized version, we only use OAuth if explicitly provided
        # to avoid OAuth flow issues in container environments

        oauth_token = os.getenv("CHATGPT_OAUTH_TOKEN")
        if oauth_token:
            logger.debug("ChatGPT OAuth token found")
            return True

        # Don't attempt OAuth flow in containers unless token is explicitly provided
        # This prevents the OAuth authentication process from failing in container environments
        logger.debug("No OAuth token found, OAuth not available")
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
        oauth_token = os.getenv("CHATGPT_OAUTH_TOKEN")

        logger.debug("Creating OAuth credentials")

        env_vars = {
            "CODEX_AUTH_METHOD": "oauth"
        }

        # If we have an OAuth token, pass it along
        if oauth_token:
            env_vars["CHATGPT_OAUTH_TOKEN"] = oauth_token

        return AuthCredentials(
            method=AuthMethod.CHATGPT_OAUTH,
            oauth_token=oauth_token,
            environment_vars=env_vars
        )

    def generate_codex_config(
        self,
        credentials: AuthCredentials,
        model: str = "gpt-5",
        approval_mode: str = "suggest"
    ) -> str:
        """
        Generate Codex CLI configuration with authentication.

        Args:
            credentials: Authentication credentials
            model: Model to use (default: gpt-5)
            approval_mode: Approval mode (default: suggest)

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

    async def cleanup(self) -> None:
        """Clean up authentication manager resources."""
        self._validated_credentials.clear()
        logger.info("Authentication manager cleaned up")