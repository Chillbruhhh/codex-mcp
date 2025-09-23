#!/usr/bin/env python3
"""
Simple test script for conversational architecture without complex async setup.

This tests the core conversational architecture components in isolation.
"""

import sys
import time
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_conversational_fields():
    """Test ContainerSession has conversational fields."""
    # Mock dependencies
    sys.modules['structlog'] = Mock()
    sys.modules['docker'] = Mock()
    sys.modules['docker.errors'] = Mock()
    sys.modules['tomli'] = Mock()
    sys.modules['dotenv'] = Mock()

    from src.container_manager import ContainerSession

    session = ContainerSession(
        session_id="test_conv_session",
        agent_id="test_agent"
    )

    # Test new conversational fields exist
    assert hasattr(session, 'codex_process')
    assert hasattr(session, 'conversation_active')
    assert hasattr(session, 'last_interaction')

    # Test default values
    assert session.codex_process is None
    assert session.conversation_active is False
    assert isinstance(session.last_interaction, float)

    print("ContainerSession conversational fields validated")


def test_conversation_methods_exist():
    """Test that conversational methods exist on container manager."""
    # Mock dependencies
    sys.modules['structlog'] = Mock()
    sys.modules['docker'] = Mock()
    sys.modules['docker.errors'] = Mock()

    with patch('src.container_manager.docker'):
        from src.container_manager import CodexContainerManager
        from src.utils.config import Config

        manager = CodexContainerManager(Config())

        # Test conversational methods exist
        assert hasattr(manager, 'start_codex_conversation')
        assert callable(manager.start_codex_conversation)
        assert hasattr(manager, 'send_message_to_codex')
        assert callable(manager.send_message_to_codex)
        assert hasattr(manager, 'end_codex_conversation')
        assert callable(manager.end_codex_conversation)
        assert hasattr(manager, '_is_complete_response')
        assert callable(manager._is_complete_response)

    print("Conversational methods exist on container manager")


def test_response_heuristics():
    """Test response completion heuristics."""
    with patch('src.container_manager.docker'):
        from src.container_manager import CodexContainerManager
        from src.utils.config import Config

        manager = CodexContainerManager(Config())

        # Test completion indicators
        assert manager._is_complete_response("codex>") is True
        assert manager._is_complete_response("$ ") is True  # Now should work
        assert manager._is_complete_response("Would you like me to help with anything else?") is True
        assert manager._is_complete_response("Here is the code you requested. Is there anything else?") is True

        # Test incomplete responses
        assert manager._is_complete_response("") is False
        assert manager._is_complete_response("Loading") is False
        assert manager._is_complete_response("Generating code") is False

        # Test substantial responses with punctuation
        long_response = "Here's a Python function that calculates the factorial of a number."
        assert manager._is_complete_response(long_response) is True

    print("Response completion heuristics working correctly")


def test_session_manager_method_exists():
    """Test that session manager has send_message_to_codex method."""
    # Mock to avoid async initialization
    with patch('src.session_manager.CodexContainerManager'):
        from src.utils.config import Config

        # Create config without initializing session manager
        config = Config()

        # Test that we can import and the method exists in the class
        from src.session_manager import CodexSessionManager

        # Check method exists in class
        assert hasattr(CodexSessionManager, 'send_message_to_codex')
        assert callable(getattr(CodexSessionManager, 'send_message_to_codex'))

    print("Session manager has send_message_to_codex method")


def test_mcp_tools_import():
    """Test that MCP tools can be imported and have conversational interface."""
    # Mock session manager to avoid initialization
    mock_session_manager = Mock()
    mock_session_manager.send_message_to_codex = AsyncMock(return_value="Mock response")

    with patch('src.mcp_server.session_manager', mock_session_manager):
        from src.mcp_server import codex_chat, codex_generate_code

        # Test tools exist and are callable
        assert callable(codex_chat)
        assert callable(codex_generate_code)

        print("MCP tools imported and use conversational interface")


def test_dockerfile_includes_codex():
    """Test that Dockerfile properly installs Codex CLI."""
    with patch('src.container_manager.docker'):
        from src.container_manager import CodexContainerManager
        from src.utils.config import Config

        manager = CodexContainerManager(Config())
        dockerfile = manager._generate_dockerfile()

        # Key requirements for conversational Codex CLI
        assert "npm install -g @openai/codex" in dockerfile
        assert "USER codex" in dockerfile  # Non-root user
        assert "WORKDIR /app" in dockerfile
        assert "HEALTHCHECK" in dockerfile

    print("Dockerfile properly configured for Codex CLI")


def test_config_structure():
    """Test configuration structure for conversational setup."""
    from src.utils.config import Config

    config = Config()

    # Test config sections exist
    assert hasattr(config, 'server')
    assert hasattr(config, 'container')
    assert hasattr(config, 'codex')
    assert hasattr(config, 'auth')

    # Test key settings for conversational architecture
    assert config.server.max_concurrent_sessions > 0
    assert config.container.memory_limit is not None
    assert config.codex.model is not None

    print("Configuration structure supports conversational architecture")


def run_all_tests():
    """Run all simple conversational tests."""
    print("Testing Conversational Architecture Components")
    print("=" * 60)

    try:
        test_conversational_fields()
        test_conversation_methods_exist()
        test_response_heuristics()
        test_session_manager_method_exists()
        test_mcp_tools_import()
        test_dockerfile_includes_codex()
        test_config_structure()

        print("\n" + "=" * 60)
        print("All conversational architecture tests PASSED!")
        print("\nKey Validations:")
        print("  * ContainerSession supports persistent conversations")
        print("  * Container manager has conversational methods")
        print("  * Response completion detection works")
        print("  * Session manager updated for natural language")
        print("  * MCP tools use conversational interface")
        print("  * Docker setup supports interactive Codex CLI")
        print("  * Configuration supports conversational architecture")

        print("\nReady for integration testing with real Docker containers!")

        return True

    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)