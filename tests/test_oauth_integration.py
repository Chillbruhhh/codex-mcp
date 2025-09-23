#!/usr/bin/env python3
"""
OAuth Integration Test Script

This script performs basic validation of the OAuth integration components
to ensure they are properly connected and functional.
"""

import sys
import asyncio
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.oauth_manager import OAuthTokenManager
from src.oauth_flow import OAuthFlow
from src.auth_manager import CodexAuthManager
from src.utils.config import get_config


async def test_oauth_integration():
    """Test OAuth integration components."""
    print("🧪 OAuth Integration Test")
    print("=" * 40)

    config = get_config()
    test_results = []

    # Test 1: OAuth Manager Initialization
    print("\n1. Testing OAuth Manager...")
    try:
        oauth_manager = OAuthTokenManager()
        token_info = oauth_manager.get_token_info()
        print(f"   ✅ OAuth Manager initialized")
        print(f"   📍 Token storage: {oauth_manager.token_path}")
        print(f"   📊 Has tokens: {token_info.get('has_tokens', False)}")
        test_results.append(("OAuth Manager", True))
    except Exception as e:
        print(f"   ❌ OAuth Manager failed: {e}")
        test_results.append(("OAuth Manager", False))

    # Test 2: OAuth Flow Initialization
    print("\n2. Testing OAuth Flow...")
    try:
        oauth_flow = OAuthFlow(oauth_manager=oauth_manager)
        flow_info = oauth_flow.get_flow_info()
        print(f"   ✅ OAuth Flow initialized")
        print(f"   📍 Client ID: {flow_info.get('client_id')}")
        print(f"   📍 Callback Port: {flow_info.get('callback_port')}")
        print(f"   📍 Auth Endpoint: {flow_info.get('authorization_endpoint')}")
        test_results.append(("OAuth Flow", True))
    except Exception as e:
        print(f"   ❌ OAuth Flow failed: {e}")
        test_results.append(("OAuth Flow", False))

    # Test 3: Auth Manager Integration
    print("\n3. Testing Auth Manager Integration...")
    try:
        auth_manager = CodexAuthManager(config)
        oauth_status = auth_manager.get_oauth_status()
        print(f"   ✅ Auth Manager initialized")
        print(f"   📊 OAuth available: {oauth_status.get('oauth_available', False)}")
        print(f"   📊 API key available: {oauth_status.get('auth_method_priority', {}).get('api_key_available', False)}")

        # Test method detection
        auth_method = auth_manager.detect_auth_method()
        print(f"   📊 Detected auth method: {auth_method.value}")
        test_results.append(("Auth Manager", True))
    except Exception as e:
        print(f"   ❌ Auth Manager failed: {e}")
        test_results.append(("Auth Manager", False))

    # Test 4: Configuration Loading
    print("\n4. Testing Configuration...")
    try:
        print(f"   ✅ Configuration loaded")
        print(f"   📍 OAuth Client ID: {config.auth.oauth.client_id}")
        print(f"   📍 OAuth Callback Port: {config.auth.oauth.callback_port}")
        print(f"   📍 Auth Method: {config.auth.auth_method}")
        print(f"   📍 Prefer OAuth: {config.auth.prefer_oauth}")
        test_results.append(("Configuration", True))
    except Exception as e:
        print(f"   ❌ Configuration failed: {e}")
        test_results.append(("Configuration", False))

    # Test 5: Authorization URL Generation
    print("\n5. Testing Authorization URL Generation...")
    try:
        # Generate URL without starting server (just test the logic)
        oauth_flow._flow_state["redirect_uri"] = f"http://localhost:{config.auth.oauth.callback_port}/callback"
        auth_url, code_verifier, state = oauth_flow.build_authorization_url()

        print(f"   ✅ Authorization URL generated")
        print(f"   📍 URL length: {len(auth_url)} chars")
        print(f"   📍 Has code verifier: {len(code_verifier) > 0}")
        print(f"   📍 Has state: {len(state) > 0}")
        print(f"   📍 URL preview: {auth_url[:80]}...")
        test_results.append(("URL Generation", True))
    except Exception as e:
        print(f"   ❌ URL Generation failed: {e}")
        test_results.append(("URL Generation", False))

    # Test Summary
    print("\n" + "=" * 40)
    print("📋 Test Summary:")
    print("=" * 40)

    passed = sum(1 for _, result in test_results if result)
    total = len(test_results)

    for test_name, result in test_results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {test_name:<20} {status}")

    print(f"\n📊 Overall: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All OAuth integration tests passed!")
        print("\n💡 Next steps:")
        print("   1. Start the server: docker-compose --profile codex-mcp up")
        print("   2. Authenticate: python auth.py login")
        return 0
    else:
        print("⚠️  Some tests failed. Please check the implementation.")
        return 1


def test_imports():
    """Test that all OAuth modules can be imported."""
    print("🧪 Import Test")
    print("=" * 20)

    imports = [
        ("OAuth Manager", "from src.oauth_manager import OAuthTokenManager"),
        ("OAuth Flow", "from src.oauth_flow import OAuthFlow"),
        ("Auth Manager Updates", "from src.auth_manager import CodexAuthManager"),
        ("Config Updates", "from src.utils.config import get_config"),
    ]

    for name, import_statement in imports:
        try:
            exec(import_statement)
            print(f"   ✅ {name}")
        except Exception as e:
            print(f"   ❌ {name}: {e}")
            return False

    print("\n✅ All imports successful!")
    return True


if __name__ == "__main__":
    print("🤖 Codex CLI MCP Server - OAuth Integration Test")
    print("=" * 50)

    # Test imports first
    if not test_imports():
        print("\n❌ Import test failed!")
        sys.exit(1)

    # Run integration tests
    try:
        result = asyncio.run(test_oauth_integration())
        sys.exit(result)
    except KeyboardInterrupt:
        print("\n❌ Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        sys.exit(1)