"""
CLI authentication commands for OAuth management.

This module provides command-line tools for managing OAuth authentication
including login, logout, status checks, and token management.
"""

import asyncio
import argparse
import sys
import json
from typing import Optional
from datetime import datetime
import structlog

try:
    # Try relative imports first (when run as module)
    from .oauth_manager import OAuthTokenManager
    from .oauth_flow import OAuthFlow
    from .auth_manager import CodexAuthManager
    from .utils.config import get_config
except ImportError:
    # Fall back to absolute imports (when run directly)
    from oauth_manager import OAuthTokenManager
    from oauth_flow import OAuthFlow
    from auth_manager import CodexAuthManager
    from utils.config import get_config

logger = structlog.get_logger(__name__)


class AuthCLI:
    """Command-line interface for OAuth authentication management."""

    def __init__(self):
        """Initialize the authentication CLI."""
        self.config = get_config()
        self.oauth_manager = OAuthTokenManager(
            self.config.auth.oauth.token_storage_path
        )
        self.oauth_flow = OAuthFlow(
            client_id=self.config.auth.oauth.client_id,
            oauth_manager=self.oauth_manager,
            callback_port=self.config.auth.oauth.callback_port
        )
        self.auth_manager = CodexAuthManager(self.config)

    async def login(
        self,
        manual: bool = False,
        no_browser: bool = False,
        timeout: int = None
    ) -> int:
        """
        Authenticate with ChatGPT subscription via OAuth.

        Args:
            manual: Use manual authorization flow
            no_browser: Don't automatically open browser
            timeout: Timeout in seconds

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        try:
            timeout = timeout or self.config.auth.oauth.callback_timeout
            auto_open_browser = self.config.auth.oauth.auto_open_browser and not no_browser

            print("🤖 Codex CLI MCP Server - ChatGPT OAuth Authentication")
            print("=" * 60)

            # Check if already authenticated
            if self.oauth_manager.has_valid_tokens():
                token_info = self.oauth_manager.get_token_info()
                if token_info.get("has_tokens") and not token_info.get("is_expired"):
                    print("✅ Already authenticated with valid tokens")
                    expires_at = token_info.get("expires_at")
                    if expires_at:
                        print(f"   Token expires: {expires_at}")

                    response = input("\nRe-authenticate? (y/N): ").strip().lower()
                    if response != 'y':
                        return 0

            if manual:
                return await self._manual_login(timeout)
            else:
                return await self._automatic_login(auto_open_browser, timeout)

        except KeyboardInterrupt:
            print("\n❌ Authentication cancelled by user")
            return 1
        except Exception as e:
            print(f"❌ Authentication failed: {e}")
            logger.error("CLI authentication failed", error=str(e))
            return 1

    async def _automatic_login(self, auto_open_browser: bool, timeout: int) -> int:
        """Run automatic OAuth flow."""
        print(f"\nStarting OAuth authentication flow...")
        print(f"Timeout: {timeout} seconds")

        if auto_open_browser:
            print("🌐 Opening browser for authentication...")
        else:
            print("🌐 Manual browser navigation required")

        async with OAuthTokenManager() as oauth_manager:
            tokens = await self.oauth_flow.run_oauth_flow(
                open_browser=auto_open_browser,
                timeout=timeout
            )

            if tokens:
                print("✅ Authentication successful!")
                print(f"   Access token expires: {datetime.fromtimestamp(tokens.expires_at)}")
                print(f"   Token storage: {oauth_manager.token_path}")
                return 0
            else:
                print("❌ Authentication failed")
                return 1

    async def _manual_login(self, timeout: int) -> int:
        """Run manual OAuth flow with copy-paste authorization."""
        print(f"\nStarting manual OAuth authentication...")
        print("This process requires copying and pasting an authorization URL.")

        try:
            # Get authorization URL
            auth_url = await self.oauth_flow.get_authorization_url()

            print("\n" + "=" * 60)
            print("STEP 1: Open this URL in your browser:")
            print("=" * 60)
            print(auth_url)
            print("=" * 60)
            print("\nSTEP 2: Complete the authorization in your browser")
            print("STEP 3: The browser will be redirected to a localhost callback")
            print(f"STEP 4: Wait up to {timeout} seconds for the callback...")

            # Wait for callback
            authorization_code = await self.oauth_flow.wait_for_callback(timeout)

            if authorization_code:
                print("✅ Authorization received!")

                # Load tokens (should have been stored by the callback)
                tokens = await self.oauth_manager.load_tokens()

                if tokens:
                    print("✅ Authentication successful!")
                    print(f"   Access token expires: {datetime.fromtimestamp(tokens.expires_at)}")
                    print(f"   Token storage: {self.oauth_manager.token_path}")
                    return 0
                else:
                    print("❌ Failed to load tokens after authorization")
                    return 1
            else:
                print("❌ Authorization timeout or failed")
                return 1

        except Exception as e:
            print(f"❌ Manual authentication failed: {e}")
            return 1

    async def logout(self, confirm: bool = False) -> int:
        """
        Revoke OAuth tokens and clear authentication.

        Args:
            confirm: Skip confirmation prompt

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        try:
            print("🤖 Codex CLI MCP Server - Logout")
            print("=" * 40)

            # Check if authenticated
            if not self.oauth_manager.has_valid_tokens():
                print("ℹ️  Not currently authenticated")
                return 0

            if not confirm:
                response = input("Revoke OAuth tokens and logout? (y/N): ").strip().lower()
                if response != 'y':
                    print("Logout cancelled")
                    return 0

            print("🔄 Revoking OAuth tokens...")

            success = await self.oauth_manager.revoke_tokens()

            if success:
                print("✅ Successfully logged out")
                print("   OAuth tokens revoked and cleared")
                return 0
            else:
                print("⚠️  Logout completed with warnings")
                print("   Local tokens cleared, but server revocation may have failed")
                return 0

        except Exception as e:
            print(f"❌ Logout failed: {e}")
            logger.error("CLI logout failed", error=str(e))
            return 1

    async def status(self, verbose: bool = False) -> int:
        """
        Show authentication status and token information.

        Args:
            verbose: Show detailed information

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        try:
            print("🤖 Codex CLI MCP Server - Authentication Status")
            print("=" * 50)

            # Get OAuth status
            oauth_status = self.auth_manager.get_oauth_status()
            token_info = self.oauth_manager.get_token_info()

            # Authentication method
            auth_method = "Unknown"
            auth_available = False

            if oauth_status.get("oauth_available"):
                auth_method = "OAuth (ChatGPT Subscription)"
                auth_available = True
            elif oauth_status.get("auth_method_priority", {}).get("api_key_available"):
                auth_method = "OpenAI API Key"
                auth_available = True

            print(f"Authentication: {auth_method}")
            print(f"Status: {'✅ Authenticated' if auth_available else '❌ Not authenticated'}")

            # OAuth token details
            if token_info.get("has_tokens"):
                print(f"\n📋 OAuth Token Details:")
                print(f"   Expired: {'❌ Yes' if token_info.get('is_expired') else '✅ No'}")

                expires_at = token_info.get("expires_at")
                if expires_at:
                    print(f"   Expires: {expires_at}")

                created_at = token_info.get("created_at")
                if created_at:
                    print(f"   Created: {created_at}")

                if token_info.get("has_refresh_token"):
                    print(f"   Refresh Token: ✅ Available")
                else:
                    print(f"   Refresh Token: ❌ Not available")

                time_until_expiry = token_info.get("time_until_expiry", 0)
                if time_until_expiry > 0:
                    hours = int(time_until_expiry // 3600)
                    minutes = int((time_until_expiry % 3600) // 60)
                    print(f"   Time until expiry: {hours}h {minutes}m")

            # Configuration
            if verbose:
                print(f"\n⚙️  Configuration:")
                print(f"   OAuth Client ID: {self.config.auth.oauth.client_id}")
                print(f"   Callback Port: {self.config.auth.oauth.callback_port}")
                print(f"   Token Storage: {self.oauth_manager.token_path}")
                print(f"   Auto Open Browser: {self.config.auth.oauth.auto_open_browser}")
                print(f"   Callback Timeout: {self.config.auth.oauth.callback_timeout}s")

                if oauth_status.get("flow_info"):
                    flow_info = oauth_status["flow_info"]
                    print(f"\n🔄 OAuth Flow Info:")
                    print(f"   Authorization Endpoint: {flow_info.get('authorization_endpoint')}")
                    print(f"   Token Endpoint: {flow_info.get('token_endpoint')}")

            return 0

        except Exception as e:
            print(f"❌ Status check failed: {e}")
            logger.error("CLI status check failed", error=str(e))
            return 1

    async def refresh(self) -> int:
        """
        Refresh OAuth tokens if possible.

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        try:
            print("🤖 Codex CLI MCP Server - Token Refresh")
            print("=" * 45)

            tokens = await self.oauth_manager.get_valid_tokens()

            if tokens:
                print("✅ Tokens refreshed successfully")
                print(f"   New expiry: {datetime.fromtimestamp(tokens.expires_at)}")
                return 0
            else:
                print("❌ Token refresh failed")
                print("   You may need to re-authenticate")
                return 1

        except Exception as e:
            print(f"❌ Token refresh failed: {e}")
            logger.error("CLI token refresh failed", error=str(e))
            return 1


async def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Codex CLI MCP Server - OAuth Authentication Management"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Login command
    login_parser = subparsers.add_parser("login", help="Authenticate with ChatGPT subscription")
    login_parser.add_argument("--manual", action="store_true",
                             help="Use manual authorization flow")
    login_parser.add_argument("--no-browser", action="store_true",
                             help="Don't automatically open browser")
    login_parser.add_argument("--timeout", type=int, metavar="SECONDS",
                             help="Authentication timeout in seconds")

    # Logout command
    logout_parser = subparsers.add_parser("logout", help="Revoke tokens and logout")
    logout_parser.add_argument("--confirm", action="store_true",
                              help="Skip confirmation prompt")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show authentication status")
    status_parser.add_argument("--verbose", "-v", action="store_true",
                              help="Show detailed information")

    # Refresh command
    refresh_parser = subparsers.add_parser("refresh", help="Refresh OAuth tokens")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    cli = AuthCLI()

    if args.command == "login":
        return await cli.login(
            manual=args.manual,
            no_browser=args.no_browser,
            timeout=args.timeout
        )
    elif args.command == "logout":
        return await cli.logout(confirm=args.confirm)
    elif args.command == "status":
        return await cli.status(verbose=args.verbose)
    elif args.command == "refresh":
        return await cli.refresh()
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n❌ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)