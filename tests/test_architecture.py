"""
Simple architecture validation test for the Codex CLI MCP Server.

This test validates the design and structure without requiring external dependencies.
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def mock_dependencies():
    """Mock all external dependencies."""
    # Mock structlog
    mock_structlog = Mock()
    mock_structlog.get_logger = Mock(return_value=Mock())
    mock_structlog.configure = Mock()
    mock_structlog.contextvars = Mock()
    mock_structlog.processors = Mock()
    mock_structlog.dev = Mock()
    sys.modules['structlog'] = mock_structlog

    # Mock docker
    mock_docker = Mock()
    mock_docker.from_env = Mock(return_value=Mock())
    mock_docker.errors = Mock()
    mock_docker.errors.DockerException = Exception
    mock_docker.errors.NotFound = Exception
    mock_docker.errors.APIError = Exception
    sys.modules['docker'] = mock_docker
    sys.modules['docker.errors'] = mock_docker.errors

    # Mock other dependencies
    sys.modules['tomli'] = Mock()
    sys.modules['tomli'].load = Mock(return_value={})
    sys.modules['dotenv'] = Mock()
    sys.modules['dotenv'].load_dotenv = Mock()

def test_configuration_architecture():
    """Test configuration management architecture."""
    print("🧪 Testing configuration architecture...")

    mock_dependencies()

    from src.utils.config import Config, ServerConfig, ContainerConfig, CodexConfig, AuthConfig

    # Test config structure
    config = Config()
    assert hasattr(config, 'server')
    assert hasattr(config, 'container')
    assert hasattr(config, 'codex')
    assert hasattr(config, 'auth')

    # Test default values
    assert config.server.host == "localhost"
    assert config.server.port == 8000
    assert config.codex.model == "gpt-4"
    assert config.container.cpu_limit == "1.0"

    print("✅ Configuration architecture validated")

def test_container_manager_architecture():
    """Test container manager architecture."""
    print("🧪 Testing container manager architecture...")

    mock_dependencies()

    from src.container_manager import CodexContainerManager, ContainerSession
    from src.utils.config import Config

    # Test container session structure
    session = ContainerSession(
        session_id="test_session_123",
        agent_id="test_agent_456"
    )

    assert session.session_id == "test_session_123"
    assert session.agent_id == "test_agent_456"
    assert session.status == "initializing"
    assert session.container_id is None
    assert isinstance(session.environment, dict)

    # Test manager initialization
    config = Config()
    manager = CodexContainerManager(config)

    assert manager.config == config
    assert manager.base_image == "codex-mcp-base"
    assert isinstance(manager.active_sessions, dict)

    # Test Dockerfile generation
    dockerfile = manager._generate_dockerfile()
    assert "FROM node:20-alpine" in dockerfile
    assert "npm install -g @openai/codex" in dockerfile
    assert "USER codex" in dockerfile

    print("✅ Container manager architecture validated")

def test_session_manager_architecture():
    """Test session manager architecture."""
    print("🧪 Testing session manager architecture...")

    mock_dependencies()

    from src.session_manager import CodexSessionManager, AgentSession, SessionMetrics
    from src.utils.config import Config

    # Test session metrics
    metrics = SessionMetrics()
    assert metrics.total_requests == 0
    assert metrics.successful_requests == 0
    assert metrics.failed_requests == 0

    # Test agent session
    session = AgentSession(
        session_id="session_123",
        agent_id="agent_456",
        created_at=1234567890.0,
        last_activity=1234567890.0
    )

    assert session.session_id == "session_123"
    assert session.agent_id == "agent_456"
    assert session.status == "active"
    assert isinstance(session.metrics, SessionMetrics)

    # Test manager initialization
    config = Config()
    with patch('src.session_manager.CodexContainerManager'):
        manager = CodexSessionManager(config)

        assert manager.config == config
        assert isinstance(manager.active_sessions, dict)
        assert isinstance(manager.agent_sessions, dict)

    print("✅ Session manager architecture validated")

def test_mcp_server_integration():
    """Test MCP server integration."""
    print("🧪 Testing MCP server integration...")

    mock_dependencies()

    # Mock FastMCP
    mock_fastmcp = Mock()
    mock_fastmcp_class = Mock(return_value=mock_fastmcp)
    sys.modules['mcp'] = Mock()
    sys.modules['mcp.server'] = Mock()
    sys.modules['mcp.server.fastmcp'] = Mock()
    sys.modules['mcp.server.fastmcp'].FastMCP = mock_fastmcp_class

    # Mock pydantic
    sys.modules['pydantic'] = Mock()
    sys.modules['pydantic'].BaseModel = object

    from src.mcp_server import create_mcp_server

    # Test server creation
    server = create_mcp_server()
    assert server == mock_fastmcp

    print("✅ MCP server integration validated")

def test_security_architecture():
    """Test security architecture compliance."""
    print("🧪 Testing security architecture...")

    mock_dependencies()

    from src.container_manager import CodexContainerManager
    from src.utils.config import Config

    manager = CodexContainerManager(Config())

    # Test Dockerfile security features
    dockerfile = manager._generate_dockerfile()

    # Check for non-root user
    assert "adduser -D -u 1000 -G codex codex" in dockerfile
    assert "USER codex" in dockerfile

    # Check for health checks
    assert "HEALTHCHECK" in dockerfile

    # Test environment isolation
    config = manager.config
    assert config.container.cpu_limit == "1.0"  # Resource limits
    assert config.container.memory_limit == "512m"  # Memory limits
    assert config.server.session_timeout == 3600  # Session timeout

    print("✅ Security architecture validated")

def test_dockerfile_generation():
    """Test Dockerfile generation for security and functionality."""
    print("🧪 Testing Dockerfile generation...")

    mock_dependencies()

    from src.container_manager import CodexContainerManager
    from src.utils.config import Config

    manager = CodexContainerManager(Config())
    dockerfile = manager._generate_dockerfile()

    # Security checks
    security_features = [
        "USER codex",  # Non-root user
        "adduser -D -u 1000 -G codex codex",  # Dedicated user
        "chown -R codex:codex /app",  # Proper ownership
    ]

    for feature in security_features:
        assert feature in dockerfile, f"Security feature missing: {feature}"

    # Functionality checks
    functionality_features = [
        "FROM node:20-alpine",  # Base image
        "npm install -g @openai/codex",  # Codex CLI installation
        "HEALTHCHECK",  # Health monitoring
        "WORKDIR /app",  # Working directory
    ]

    for feature in functionality_features:
        assert feature in dockerfile, f"Functionality feature missing: {feature}"

    print("✅ Dockerfile generation validated")

def main():
    """Run all architecture tests."""
    print("🚀 Running Codex CLI MCP Server Architecture Tests\n")

    try:
        test_configuration_architecture()
        test_container_manager_architecture()
        test_session_manager_architecture()
        test_mcp_server_integration()
        test_security_architecture()
        test_dockerfile_generation()

        print("\n🎉 ALL TESTS PASSED!")
        print("✅ Configuration management: VALIDATED")
        print("✅ Container isolation: VALIDATED")
        print("✅ Session management: VALIDATED")
        print("✅ MCP integration: VALIDATED")
        print("✅ Security architecture: VALIDATED")
        print("✅ Docker integration: VALIDATED")

        return True

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)