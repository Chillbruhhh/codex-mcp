"""
OAuth manager for ChatGPT subscription authentication.

This module handles OAuth flow, token storage, refresh, and management for
integrating with ChatGPT subscription authentication, allowing users to use
their ChatGPT quota instead of separate OpenAI API billing.
"""

import asyncio
import json
import time
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
import aiohttp
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class OAuthTokens:
    """OAuth token data structure matching Codex CLI format."""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_in: int = 3600  # Default 1 hour
    expires_at: float = 0.0  # Timestamp when token expires
    scope: Optional[str] = None
    created_at: float = 0.0  # When tokens were created
    extra: Dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        """Set timestamps if not provided."""
        if self.created_at == 0.0:
            self.created_at = time.time()
        if self.expires_at == 0.0:
            self.expires_at = self.created_at + self.expires_in

    def is_expired(self, buffer_seconds: int = 300) -> bool:
        """Check if token is expired with optional buffer."""
        return time.time() >= (self.expires_at - buffer_seconds)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format, preserving extra fields."""
        base = {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_type": self.token_type,
            "expires_in": self.expires_in,
            "expires_at": self.expires_at,
            "scope": self.scope,
            "created_at": self.created_at,
        }
        base.update(self.extra)
        return base

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OAuthTokens":
        """Create from dictionary data, ignoring unknown fields."""
        allowed_fields = {
            "access_token",
            "refresh_token",
            "token_type",
            "expires_in",
            "expires_at",
            "scope",
            "created_at",
        }

        filtered = {k: v for k, v in data.items() if k in allowed_fields}
        extra = {k: v for k, v in data.items() if k not in allowed_fields}
        instance = cls(**filtered)
        instance.extra = extra
        return instance


class OAuthError(Exception):
    """Base class for OAuth-related errors."""
    pass


class OAuthTokenExpired(OAuthError):
    """Raised when OAuth token is expired and cannot be refreshed."""
    pass


class OAuthTokenManager:
    """
    Manages OAuth tokens for ChatGPT subscription authentication.

    Handles token storage, refresh, and validation using the same format
    as the official Codex CLI to ensure compatibility.
    """

    def __init__(self, token_storage_path: Optional[str] = None):
        """
        Initialize OAuth token manager.

        Args:
            token_storage_path: Custom path for token storage.
                              Defaults to ~/.codex/auth.json
        """
        if token_storage_path:
            self.token_path = Path(token_storage_path)
        else:
            # Use same path as official Codex CLI
            codex_home = Path.home() / ".codex"
            codex_home.mkdir(exist_ok=True)
            self.token_path = codex_home / "auth.json"

        self._tokens: Optional[OAuthTokens] = None
        self._session: Optional[aiohttp.ClientSession] = None

        # OAuth endpoints - these would need to be the actual OpenAI OAuth endpoints
        self.auth_base_url = "https://auth.openai.com"
        self.token_endpoint = f"{self.auth_base_url}/oauth/token"
        self.revoke_endpoint = f"{self.auth_base_url}/oauth/revoke"

        logger.info("OAuth token manager initialized",
                   token_path=str(self.token_path))

    async def __aenter__(self):
        """Async context manager entry."""
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._session:
            await self._session.close()

    async def load_tokens(self) -> Optional[OAuthTokens]:
        """
        Load tokens from storage.

        Returns:
            OAuthTokens if found and valid, None otherwise
        """
        try:
            if not self.token_path.exists():
                logger.debug("No token file found", path=str(self.token_path))
                return None

            with open(self.token_path, 'r') as f:
                data = json.load(f)

            # Handle both new format and legacy format
            if 'tokens' in data and data['tokens']:
                token_data = data['tokens']
            elif 'access_token' in data:
                token_data = data
            else:
                logger.warning("Invalid token file format")
                return None

            tokens = OAuthTokens.from_dict(token_data)
            self._tokens = tokens

            logger.debug("Tokens loaded successfully",
                        expires_at=datetime.fromtimestamp(tokens.expires_at),
                        is_expired=tokens.is_expired())

            return tokens

        except Exception as e:
            logger.error("Failed to load tokens", error=str(e))
            return None

    async def save_tokens(self, tokens: OAuthTokens) -> None:
        """
        Save tokens to storage in Codex CLI compatible format.

        Args:
            tokens: OAuth tokens to save
        """
        try:
            # Ensure directory exists
            self.token_path.parent.mkdir(parents=True, exist_ok=True)

            # Save in format compatible with Codex CLI
            auth_data = {
                "OPENAI_API_KEY": None,  # OAuth mode doesn't use API key
                "tokens": tokens.to_dict(),
                "last_refresh": time.time()
            }

            # Write atomically by writing to temp file then moving
            temp_path = self.token_path.with_suffix('.tmp')
            with open(temp_path, 'w') as f:
                json.dump(auth_data, f, indent=2)

            # Atomic move
            temp_path.replace(self.token_path)

            # Set restrictive permissions
            self.token_path.chmod(0o600)

            self._tokens = tokens

            logger.info("Tokens saved successfully",
                       path=str(self.token_path),
                       expires_at=datetime.fromtimestamp(tokens.expires_at))

        except Exception as e:
            logger.error("Failed to save tokens", error=str(e))
            raise OAuthError(f"Token save failed: {e}")

    async def get_valid_tokens(self) -> Optional[OAuthTokens]:
        """
        Get valid tokens, refreshing if necessary.

        Returns:
            Valid OAuthTokens or None if unavailable
        """
        # Load tokens if not already loaded
        if self._tokens is None:
            self._tokens = await self.load_tokens()

        if self._tokens is None:
            logger.debug("No tokens available")
            return None

        # Check if tokens are expired
        if self._tokens.is_expired():
            logger.info("Tokens expired, attempting refresh")

            if self._tokens.refresh_token:
                try:
                    refreshed = await self.refresh_tokens(self._tokens.refresh_token)
                    if refreshed:
                        self._tokens = refreshed
                        await self.save_tokens(refreshed)
                        logger.info("Tokens refreshed successfully")
                        return refreshed
                except Exception as e:
                    logger.error("Token refresh failed", error=str(e))

            logger.warning("Unable to refresh expired tokens")
            return None

        logger.debug("Valid tokens available")
        return self._tokens

    async def refresh_tokens(self, refresh_token: str) -> Optional[OAuthTokens]:
        """
        Refresh OAuth tokens using refresh token.

        Args:
            refresh_token: Refresh token for getting new access token

        Returns:
            New OAuthTokens if successful, None otherwise
        """
        if not self._session:
            self._session = aiohttp.ClientSession()

        try:
            refresh_data = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": "codex-cli",  # Would need actual client ID
            }

            async with self._session.post(
                self.token_endpoint,
                data=refresh_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            ) as response:

                if response.status == 200:
                    token_data = await response.json()

                    # Create new tokens object
                    new_tokens = OAuthTokens(
                        access_token=token_data["access_token"],
                        refresh_token=token_data.get("refresh_token", refresh_token),
                        token_type=token_data.get("token_type", "Bearer"),
                        expires_in=token_data.get("expires_in", 3600),
                        scope=token_data.get("scope")
                    )

                    logger.info("Token refresh successful",
                               expires_in=new_tokens.expires_in)
                    return new_tokens

                else:
                    error_text = await response.text()
                    logger.error("Token refresh failed",
                               status=response.status,
                               error=error_text)
                    return None

        except Exception as e:
            logger.error("Token refresh error", error=str(e))
            return None

    async def store_tokens_from_code(
        self,
        authorization_code: str,
        code_verifier: str,
        redirect_uri: str
    ) -> Optional[OAuthTokens]:
        """
        Exchange authorization code for tokens and store them.

        Args:
            authorization_code: Authorization code from OAuth flow
            code_verifier: PKCE code verifier
            redirect_uri: Redirect URI used in OAuth flow

        Returns:
            OAuthTokens if successful, None otherwise
        """
        if not self._session:
            self._session = aiohttp.ClientSession()

        try:
            token_data = {
                "grant_type": "authorization_code",
                "code": authorization_code,
                "redirect_uri": redirect_uri,
                "client_id": "codex-cli",  # Would need actual client ID
                "code_verifier": code_verifier,
            }

            async with self._session.post(
                self.token_endpoint,
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            ) as response:

                if response.status == 200:
                    token_response = await response.json()

                    tokens = OAuthTokens(
                        access_token=token_response["access_token"],
                        refresh_token=token_response.get("refresh_token"),
                        token_type=token_response.get("token_type", "Bearer"),
                        expires_in=token_response.get("expires_in", 3600),
                        scope=token_response.get("scope")
                    )

                    await self.save_tokens(tokens)

                    logger.info("OAuth tokens obtained and stored successfully")
                    return tokens

                else:
                    error_text = await response.text()
                    logger.error("Token exchange failed",
                               status=response.status,
                               error=error_text)
                    return None

        except Exception as e:
            logger.error("Token exchange error", error=str(e))
            return None

    async def revoke_tokens(self) -> bool:
        """
        Revoke stored tokens and clear from storage.

        Returns:
            True if successful, False otherwise
        """
        tokens = await self.load_tokens()
        if not tokens:
            logger.debug("No tokens to revoke")
            return True

        if not self._session:
            self._session = aiohttp.ClientSession()

        success = True

        # Revoke access token
        try:
            async with self._session.post(
                self.revoke_endpoint,
                data={
                    "token": tokens.access_token,
                    "token_type_hint": "access_token"
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            ) as response:
                if response.status not in [200, 204]:
                    logger.warning("Access token revocation failed",
                                 status=response.status)
                    success = False
        except Exception as e:
            logger.error("Failed to revoke access token", error=str(e))
            success = False

        # Revoke refresh token if present
        if tokens.refresh_token:
            try:
                async with self._session.post(
                    self.revoke_endpoint,
                    data={
                        "token": tokens.refresh_token,
                        "token_type_hint": "refresh_token"
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                ) as response:
                    if response.status not in [200, 204]:
                        logger.warning("Refresh token revocation failed",
                                     status=response.status)
                        success = False
            except Exception as e:
                logger.error("Failed to revoke refresh token", error=str(e))
                success = False

        # Clear local storage regardless of revocation success
        try:
            if self.token_path.exists():
                self.token_path.unlink()
            self._tokens = None
            logger.info("Local token storage cleared")
        except Exception as e:
            logger.error("Failed to clear token storage", error=str(e))
            success = False

        return success

    def has_valid_tokens(self) -> bool:
        """
        Synchronously check if valid tokens are available.

        Returns:
            True if tokens exist and are not expired
        """
        if not self.token_path.exists():
            return False

        try:
            with open(self.token_path, 'r') as f:
                data = json.load(f)

            if 'tokens' not in data or not data['tokens']:
                return False

            token_data = data['tokens']
            tokens = OAuthTokens.from_dict(token_data)

            return not tokens.is_expired()

        except Exception:
            return False

    def get_token_info(self) -> Dict[str, Any]:
        """
        Get information about stored tokens.

        Returns:
            Dictionary with token information
        """
        if not self.token_path.exists():
            return {
                "has_tokens": False,
                "message": "No tokens stored"
            }

        try:
            with open(self.token_path, 'r') as f:
                data = json.load(f)

            if 'tokens' not in data or not data['tokens']:
                return {
                    "has_tokens": False,
                    "message": "Invalid token format"
                }

            token_data = data['tokens']
            tokens = OAuthTokens.from_dict(token_data)

            return {
                "has_tokens": True,
                "is_expired": tokens.is_expired(),
                "expires_at": datetime.fromtimestamp(tokens.expires_at).isoformat(),
                "created_at": datetime.fromtimestamp(tokens.created_at).isoformat(),
                "has_refresh_token": tokens.refresh_token is not None,
                "scope": tokens.scope,
                "time_until_expiry": max(0, tokens.expires_at - time.time())
            }

        except Exception as e:
            return {
                "has_tokens": False,
                "message": f"Error reading tokens: {e}"
            }
