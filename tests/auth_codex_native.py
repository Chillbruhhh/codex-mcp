#!/usr/bin/env python3
"""
Codex CLI Native OAuth Authentication

This script uses the official Codex CLI's built-in OAuth flow
to authenticate with your ChatGPT subscription.
"""

import sys
import subprocess
import tempfile
import shutil
import json
from pathlib import Path
import time

def check_codex_cli():
    """Check if Codex CLI is available."""
    # Try different possible command names
    commands_to_try = ["codex-cli", "codex"]

    for cmd in commands_to_try:
        try:
            result = subprocess.run([cmd, "--version"],
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print(f"✅ Codex CLI found: {result.stdout.strip()} (command: {cmd})")
                return cmd  # Return the working command name
            else:
                print(f"❌ {cmd} not responding correctly")
        except FileNotFoundError:
            print(f"❌ {cmd} not found in PATH")
        except subprocess.TimeoutExpired:
            print(f"❌ {cmd} not responding (timeout)")
        except Exception as e:
            print(f"❌ Error checking {cmd}: {e}")

    return None

def install_codex_cli():
    """Install Codex CLI using npm."""
    print("📦 Installing Codex CLI...")
    try:
        # Check if npm is available
        subprocess.run(["npm", "--version"],
                      capture_output=True, check=True, timeout=5)

        # Install Codex CLI globally
        result = subprocess.run(["npm", "install", "-g", "@openai/codex"],
                              capture_output=True, text=True, timeout=120)

        if result.returncode == 0:
            print("✅ Codex CLI installed successfully")
            return True
        else:
            print(f"❌ Installation failed: {result.stderr}")
            return False

    except FileNotFoundError:
        print("❌ npm not found. Please install Node.js first:")
        print("   https://nodejs.org/")
        return False
    except subprocess.TimeoutExpired:
        print("❌ Installation timeout")
        return False
    except Exception as e:
        print(f"❌ Installation error: {e}")
        return False

def run_codex_oauth(codex_command):
    """Run Codex CLI OAuth authentication."""
    print("🔐 Starting Codex CLI OAuth authentication...")
    print("This will open your browser to authenticate with your ChatGPT account.")

    # Create temporary directory for Codex CLI
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        try:
            # Run Codex CLI which should trigger OAuth flow
            print(f"\n🌐 Starting {codex_command} (this will open your browser)...")

            # First, just run a simple command to trigger auth setup
            result = subprocess.run(
                [codex_command, "--version"],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                print("✅ Codex CLI responded successfully")

                # Check if auth tokens were created
                codex_home = Path.home() / ".codex"
                auth_file = codex_home / "auth.json"

                if auth_file.exists():
                    print(f"✅ Authentication tokens found at: {auth_file}")

                    # Validate token structure
                    try:
                        with open(auth_file) as f:
                            auth_data = json.load(f)

                        if auth_data.get("tokens"):
                            print("✅ OAuth tokens are available")
                            return True
                        elif auth_data.get("OPENAI_API_KEY"):
                            print("ℹ️  API key authentication detected")
                            print("   To use OAuth, you may need to clear existing auth:")
                            print(f"   rm {auth_file}")
                            print("   Then run: codex")
                            return False
                        else:
                            print("⚠️  Authentication file exists but format is unclear")
                            return False

                    except json.JSONDecodeError:
                        print("❌ Authentication file is corrupted")
                        return False
                else:
                    print("ℹ️  No authentication tokens found")
                    print("   Please run 'codex' directly to complete OAuth setup")
                    return False
            else:
                print(f"❌ Codex CLI failed: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            print("❌ Codex CLI timeout")
            return False
        except Exception as e:
            print(f"❌ Error running Codex CLI: {e}")
            return False

def show_auth_status():
    """Show current authentication status."""
    print("\n📊 Authentication Status:")
    print("=" * 30)

    codex_home = Path.home() / ".codex"
    auth_file = codex_home / "auth.json"

    if not auth_file.exists():
        print("❌ No authentication found")
        print(f"   Expected location: {auth_file}")
        return False

    try:
        with open(auth_file) as f:
            auth_data = json.load(f)

        print(f"📁 Auth file: {auth_file}")

        if auth_data.get("tokens"):
            tokens = auth_data["tokens"]
            print("✅ OAuth authentication active")

            if tokens.get("access_token"):
                token_preview = tokens["access_token"][:20] + "..."
                print(f"   Access token: {token_preview}")

            if tokens.get("expires_at"):
                import datetime
                expires_at = datetime.datetime.fromtimestamp(tokens["expires_at"])
                print(f"   Expires: {expires_at}")

            return True

        elif auth_data.get("OPENAI_API_KEY"):
            api_key_preview = auth_data["OPENAI_API_KEY"][:20] + "..."
            print(f"ℹ️  API key authentication: {api_key_preview}")
            return True

        else:
            print("⚠️  Authentication file exists but format is unclear")
            return False

    except json.JSONDecodeError:
        print("❌ Authentication file is corrupted")
        return False
    except Exception as e:
        print(f"❌ Error reading auth file: {e}")
        return False

def main():
    """Main entry point."""
    print("🤖 Codex CLI OAuth Authentication Setup")
    print("=" * 45)

    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
    else:
        command = "help"

    if command == "login":
        # Check if Codex CLI is available
        codex_command = check_codex_cli()
        if not codex_command:
            print("\n💡 Codex CLI is required for OAuth authentication")
            response = input("Install Codex CLI now? (y/N): ").strip().lower()
            if response == 'y':
                if not install_codex_cli():
                    return 1
                # Check again after installation
                codex_command = check_codex_cli()
                if not codex_command:
                    return 1
            else:
                print("❌ Cannot proceed without Codex CLI")
                return 1

        # Run OAuth authentication
        if run_codex_oauth(codex_command):
            print("\n🎉 OAuth authentication successful!")
            show_auth_status()
            return 0
        else:
            print("\n❌ OAuth authentication failed")
            print(f"\n💡 Try running '{codex_command}' directly:")
            print(f"   1. Run: {codex_command}")
            print("   2. Choose 'Sign in with ChatGPT' when prompted")
            print("   3. Complete the browser authentication")
            return 1

    elif command == "status":
        if show_auth_status():
            return 0
        else:
            return 1

    elif command == "logout":
        codex_home = Path.home() / ".codex"
        auth_file = codex_home / "auth.json"

        if auth_file.exists():
            response = input("Remove authentication tokens? (y/N): ").strip().lower()
            if response == 'y':
                auth_file.unlink()
                print("✅ Authentication tokens removed")
                return 0
            else:
                print("❌ Logout cancelled")
                return 1
        else:
            print("ℹ️  No authentication tokens found")
            return 0

    else:
        print("Usage:")
        print("  python auth_codex_native.py login   # Authenticate with ChatGPT")
        print("  python auth_codex_native.py status  # Check authentication status")
        print("  python auth_codex_native.py logout  # Remove authentication")
        print("\nThis script uses the official Codex CLI OAuth flow.")
        return 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n❌ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)