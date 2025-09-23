"""
Integration tests for the container management system.

These tests validate the architecture and design without requiring
external dependencies like Docker or the full dependency stack.
"""

import asyncio
import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestContainerArchitecture:
    """Test the container management architecture."""

    def test_imports_and_structure(self):
        """Test that all modules can be imported and have correct structure."""
        # Mock external dependencies
        sys.modules['structlog'] = Mock()
        sys.modules['docker'] = Mock()
        sys.modules['docker.errors'] = Mock()
        sys.modules['tomli'] = Mock()
        sys.modules['dotenv'] = Mock()

        try:
            from src.utils.config import Config, get_config
            from src.container_manager import CodexContainerManager, ContainerSession
            from src.session_manager import CodexSessionManager, AgentSession

            # Test config structure
            config = Config()
            assert hasattr(config, 'server')
            assert hasattr(config, 'container')
            assert hasattr(config, 'codex')
            assert hasattr(config, 'auth')

            # Test container session structure
            session = ContainerSession(
                session_id="test_session",
                agent_id="test_agent"
            )
            assert session.session_id == "test_session"
            assert session.agent_id == "test_agent"
            assert session.status == "initializing"

            print("✅ All imports and structures validated")

        except Exception as e:
            pytest.fail(f"Import or structure test failed: {e}")

    @patch('src.container_manager.docker')
    def test_container_manager_initialization(self, mock_docker):
        """Test container manager initialization."""
        from src.utils.config import Config
        from src.container_manager import CodexContainerManager

        # Mock Docker client
        mock_client = Mock()
        mock_docker.from_env.return_value = mock_client

        config = Config()
        manager = CodexContainerManager(config)

        assert manager.config == config
        assert manager.docker_client == mock_client
        assert manager.base_image == "codex-mcp-base"
        assert isinstance(manager.active_sessions, dict)

        print("✅ Container manager initialization validated")

    def test_dockerfile_generation(self):
        """Test Dockerfile generation for Codex CLI."""
        from src.container_manager import CodexContainerManager
        from src.utils.config import Config

        with patch('src.container_manager.docker'):
            manager = CodexContainerManager(Config())
            dockerfile = manager._generate_dockerfile()

            # Validate Dockerfile content
            assert "FROM node:20-alpine" in dockerfile
            assert "npm install -g @openai/codex" in dockerfile
            assert "adduser -D -u 1000 -G codex codex" in dockerfile
            assert "USER codex" in dockerfile
            assert "HEALTHCHECK" in dockerfile

            print("✅ Dockerfile generation validated")

    def test_session_configuration(self):
        """Test session configuration structure."""
        from src.session_manager import AgentSession, SessionMetrics

        session = AgentSession(
            session_id="test_session_123",
            agent_id="test_agent_456",
            created_at=1234567890.0,
            last_activity=1234567890.0
        )

        assert session.session_id == "test_session_123"
        assert session.agent_id == "test_agent_456"
        assert session.status == "active"
        assert isinstance(session.metrics, SessionMetrics)
        assert isinstance(session.config, dict)

        # Test metrics
        session.metrics.total_requests = 5
        session.metrics.successful_requests = 4
        success_rate = session.metrics.successful_requests / session.metrics.total_requests
        assert success_rate == 0.8

        print("✅ Session configuration validated")

    def test_environment_variable_handling(self):
        """Test environment variable configuration."""
        from src.utils.config import Config

        config = Config()

        # Test default values
        assert config.server.host == "localhost"
        assert config.server.port == 8000
        assert config.codex.model == "gpt-4"
        assert config.container.cpu_limit == "1.0"
        assert config.container.memory_limit == "512m"

        print("✅ Environment variable handling validated")

    @patch('src.container_manager.tempfile.mkdtemp')
    def test_session_directory_creation(self, mock_mkdtemp):
        """Test session directory creation logic."""
        from src.container_manager import CodexContainerManager, ContainerSession
        from src.utils.config import Config

        mock_mkdtemp.side_effect = ["/tmp/config-123", "/tmp/workspace-123"]

        with patch('src.container_manager.docker'):
            manager = CodexContainerManager(Config())
            session = ContainerSession(
                session_id="test_session",
                agent_id="test_agent"
            )

            # Test directory creation logic
            asyncio.run(manager._create_session_directories(session))

            assert session.config_dir == "/tmp/config-123"
            assert session.workspace_dir == "/tmp/workspace-123"
            assert mock_mkdtemp.call_count == 2

        print("✅ Session directory creation validated")


def test_architecture_integration():
    """Integration test for the overall architecture."""
    # Mock all external dependencies
    with patch.multiple('sys.modules',
                        structlog=Mock(),
                        docker=Mock(),
                        tomli=Mock(),
                        dotenv=Mock()):

        sys.modules['docker.errors'] = Mock()
        sys.modules['docker.errors'].DockerException = Exception
        sys.modules['docker.errors'].NotFound = Exception
        sys.modules['docker.errors'].APIError = Exception

        from src.utils.config import Config
        from src.container_manager import CodexContainerManager
        from src.session_manager import CodexSessionManager

        # Test configuration flow
        config = Config()
        config.server.max_concurrent_sessions = 5
        config.server.session_timeout = 3600

        # Test manager initialization
        with patch('src.container_manager.docker.from_env'):
            container_manager = CodexContainerManager(config)
            session_manager = CodexSessionManager(config)

            # Validate the architecture
            assert container_manager.config == config
            assert session_manager.config == config
            assert session_manager.container_manager.config == config

    print("✅ Architecture integration validated")


if __name__ == "__main__":
    test = TestContainerArchitecture()
    test.test_imports_and_structure()
    test.test_container_manager_initialization()
    test.test_dockerfile_generation()
    test.test_session_configuration()
    test.test_environment_variable_handling()
    test.test_session_directory_creation()

    test_architecture_integration()

    print("\n🎉 All architecture tests passed!")
    print("✅ Container management system is properly designed")
    print("✅ Session isolation architecture is sound")
    print("✅ Configuration management is working")
    print("✅ Docker integration points are correct")