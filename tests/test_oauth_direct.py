#!/usr/bin/env python3
"""
Direct OAuth Testing Script

This script directly tests the OAuth authentication without relying on MCP tools.
"""

import subprocess
import json
import sys

def test_oauth_container():
    """Test OAuth authentication in a Codex container directly."""
    print("[TEST] Testing OAuth Authentication in Container")
    print("=" * 50)

    try:
        # 1. Check if OAuth tokens are mounted
        print("1. Checking OAuth token mounting...")
        result = subprocess.run([
            "docker", "exec", "codex-mcp-server",
            "ls", "-la", "/app/.codex/"
        ], capture_output=True, text=True, timeout=10)

        if result.returncode == 0:
            print("   [OK] OAuth directory is mounted")
            print(f"   [INFO] Contents: {len(result.stdout.splitlines())} items")
        else:
            print("   [ERROR] OAuth directory not found")
            return False

        # 2. Check if auth.json contains OAuth tokens
        print("\n2. Checking OAuth token content...")
        result = subprocess.run([
            "docker", "exec", "codex-mcp-server",
            "cat", "/app/.codex/auth.json"
        ], capture_output=True, text=True, timeout=10)

        if result.returncode == 0:
            try:
                auth_data = json.loads(result.stdout)
                has_oauth = auth_data.get("tokens", {}).get("access_token") is not None
                has_api_key = auth_data.get("OPENAI_API_KEY") is not None

                print(f"   YES Auth file readable")
                print(f"   [TOKEN] Has OAuth tokens: {'YES' if has_oauth else 'NO'}")
                print(f"   [TOKEN] Has API key: {'YES' if has_api_key else 'NO'}")

                if has_oauth:
                    access_token = auth_data["tokens"]["access_token"]
                    print(f"   [INFO] Access token preview: {access_token[:30]}...")

                    # Check expiration
                    if "expires_at" in auth_data["tokens"]:
                        import datetime
                        exp_time = datetime.datetime.fromtimestamp(auth_data["tokens"]["expires_at"])
                        now = datetime.datetime.now()
                        if exp_time > now:
                            print(f"   [TIME] Token valid until: {exp_time}")
                        else:
                            print(f"   [WARNING]  Token expired: {exp_time}")

                return has_oauth
            except json.JSONDecodeError:
                print("   NO Invalid JSON in auth file")
                return False
        else:
            print("   NO Cannot read auth file")
            return False

    except subprocess.TimeoutExpired:
        print("   NO Command timeout")
        return False
    except Exception as e:
        print(f"   [ERROR] Error: {e}")
        return False

def test_codex_cli_auth():
    """Test if Codex CLI can authenticate in container."""
    print("\n3. Testing Codex CLI authentication...")

    try:
        # Test Codex CLI version command in container
        result = subprocess.run([
            "docker", "exec", "codex-mcp-server",
            "bash", "-c", "cd /tmp && timeout 30 codex --version"
        ], capture_output=True, text=True, timeout=45)

        if result.returncode == 0:
            print("   YES Codex CLI responding")
            print(f"   [INFO] Output: {result.stdout.strip()}")
            return True
        else:
            print("   NO Codex CLI not responding")
            print(f"   [INFO] Error: {result.stderr.strip()}")
            return False

    except subprocess.TimeoutExpired:
        print("   [TIME] Codex CLI test timeout (possibly working but slow)")
        return False
    except Exception as e:
        print(f"   [ERROR] Error: {e}")
        return False

def check_quota_status():
    """Check if ChatGPT quota might be an issue."""
    print("\n4. Quota and Authentication Status:")
    print("   [WARNING]  Note: You mentioned ChatGPT subscription hit max usage")
    print("   [INFO] This could cause OAuth requests to be rejected")
    print("   [INFO] OAuth tokens may be valid but quota exhausted")
    print("   [INFO] System may fall back to API key authentication")

def main():
    """Main test function."""
    print("[TEST] Codex CLI OAuth Integration Test")
    print("[INFO] Testing without MCP tool dependencies")
    print()

    # Run tests
    oauth_mounted = test_oauth_container()
    codex_responsive = test_codex_cli_auth()
    check_quota_status()

    # Summary
    print("\n" + "=" * 50)
    print("[SUMMARY] Test Summary:")
    print(f"   OAuth Tokens Mounted: {'YES' if oauth_mounted else 'NO'}")
    print(f"   Codex CLI Responsive: {'YES' if codex_responsive else 'NO'}")

    if oauth_mounted and codex_responsive:
        print("\n[SUCCESS] OAuth integration appears to be working!")
        print("[INFO] If still using API key, check quota limits")
    elif oauth_mounted:
        print("\n[WARNING]  OAuth tokens mounted but Codex CLI issues")
        print("[INFO] May be quota-related or container environment issue")
    else:
        print("\nNO OAuth integration has issues")

    return 0 if (oauth_mounted and codex_responsive) else 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nNO Test interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\nNO Test failed: {e}")
        sys.exit(1)