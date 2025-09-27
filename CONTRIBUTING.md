# Contributing to Codex CLI MCP Server

Thank you for your interest in contributing to the Codex CLI MCP Server project. This document provides comprehensive guidelines for contributors to ensure high-quality contributions and maintain project standards.

## Table of Contents

- [Development Environment Setup](#development-environment-setup)
- [Project Structure](#project-structure)
- [Code Standards](#code-standards)
- [Testing Requirements](#testing-requirements)
- [Pull Request Process](#pull-request-process)
- [Issue Guidelines](#issue-guidelines)
- [Security Considerations](#security-considerations)
- [Documentation Standards](#documentation-standards)

## Development Environment Setup

### Prerequisites

- **Python 3.12+** with pip and venv
- **Docker Engine 20.10+** with Docker Compose v2.0+
- **Git** for version control
- **Node.js 18+** (for MCP testing tools)
- **VS Code** or similar IDE with Python extensions

### Initial Setup

```bash
# Clone the repository
git clone https://github.com/your-org/codex-mcp-server.git
cd codex-mcp-server

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development dependencies
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install

# Set up environment variables
cp .env.example .env
# Edit .env with your configuration
```

### Development Dependencies

Required packages for development:

```bash
# Core development tools
pytest>=7.0.0
pytest-asyncio>=0.21.0
pytest-cov>=4.0.0
black>=23.0.0
isort>=5.12.0
flake8>=6.0.0
mypy>=1.5.0

# Testing and mocking
pytest-docker>=2.0.0
httpx>=0.25.0
respx>=0.20.0

# Documentation
mkdocs>=1.5.0
mkdocs-material>=9.0.0

# MCP testing
@modelcontextprotocol/inspector
```

## Project Structure

### Directory Organization

```
src/
├── mcp_server.py          # FastMCP server (MAX 500 lines)
├── container_manager.py   # Docker lifecycle (MAX 400 lines)
├── session_manager.py     # Agent sessions (MAX 300 lines)
├── auth_manager.py        # Authentication (MAX 250 lines)
├── direct_codex_tools.py  # Direct tool implementations
├── interactive_codex_manager.py  # Interactive sessions
├── async_docker_manager.py      # Async Docker operations
└── utils/                 # Helper modules (MAX 150 lines each)
    ├── config.py
    ├── logging.py
    └── validators.py

tests/
├── unit/                  # Unit tests
├── integration/           # Integration tests
├── fixtures/              # Test fixtures
└── conftest.py           # Pytest configuration

docs/                      # Documentation
scripts/                   # Utility scripts
docker/                    # Docker configurations
```

### File Size Limits

- **Main modules**: Maximum 500 lines
- **Helper modules**: Maximum 150 lines
- **Test files**: No strict limit but prefer focused test files
- **Split large files** into logical modules when approaching limits

## Code Standards

### Python Style Guidelines

#### Type Hints
```python
# Always use type hints
from typing import Optional, List, Dict, Any
from datetime import datetime

async def process_request(
    agent_id: str,
    data: Dict[str, Any],
    timeout: Optional[int] = None
) -> Dict[str, Any]:
    """Process agent request with proper typing."""
    pass
```

#### Docstring Format
```python
def create_container(self, config: ContainerConfig) -> Container:
    """
    Create and configure a new agent container.

    Args:
        config: Container configuration including image, resources, and environment

    Returns:
        Container: Configured container instance ready for agent use

    Raises:
        ContainerCreationError: If container creation fails
        ResourceExhaustedError: If system resources are insufficient

    Example:
        >>> config = ContainerConfig(image="codex:latest", memory="2G")
        >>> container = manager.create_container(config)
        >>> container.start()
    """
```

#### Error Handling
```python
# Use specific exception types
class MCPServerError(Exception):
    """Base exception for MCP server errors."""
    pass

class ContainerCreationError(MCPServerError):
    """Raised when container creation fails."""
    pass

# Proper error context
try:
    container = await self.create_container(config)
except DockerException as e:
    logger.error("Container creation failed", agent_id=agent_id, error=str(e))
    raise ContainerCreationError(f"Failed to create container for {agent_id}: {e}")
```

#### Async Programming
```python
# Use async/await consistently
async def process_codex_request(self, message: str) -> str:
    """Process request with proper async handling."""
    async with self.session_manager.get_session(self.agent_id) as session:
        try:
            result = await asyncio.wait_for(
                session.send_message(message),
                timeout=self.config.timeout
            )
            return result
        except asyncio.TimeoutError:
            raise TimeoutError(f"Request timed out after {self.config.timeout}s")
```

### Code Quality Requirements

#### Formatting
- **Black** for code formatting with 88-character line limit
- **isort** for import sorting
- **flake8** for linting with specific configuration

#### Configuration Files
```ini
# pyproject.toml
[tool.black]
line-length = 88
target-version = ['py312']

[tool.isort]
profile = "black"
multi_line_output = 3

[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
```

## Testing Requirements

### Test Coverage Standards

- **Minimum 80% code coverage** for all new code
- **100% coverage required** for critical paths (authentication, container management)
- **Unit tests** for all public methods
- **Integration tests** for MCP protocol compliance
- **Security tests** for authentication and isolation

### Test Structure

#### Unit Tests
```python
# tests/unit/test_container_manager.py
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_create_container_success():
    """Test successful container creation."""
    manager = ContainerManager(config=test_config)

    with patch('docker.DockerClient') as mock_docker:
        mock_container = AsyncMock()
        mock_docker.return_value.containers.create.return_value = mock_container

        result = await manager.create_container(test_config)

        assert result == mock_container
        mock_docker.return_value.containers.create.assert_called_once()

@pytest.mark.asyncio
async def test_create_container_docker_error():
    """Test container creation with Docker error."""
    manager = ContainerManager(config=test_config)

    with patch('docker.DockerClient') as mock_docker:
        mock_docker.return_value.containers.create.side_effect = DockerException("Error")

        with pytest.raises(ContainerCreationError):
            await manager.create_container(test_config)
```

#### Integration Tests
```python
# tests/integration/test_mcp_protocol.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_mcp_tool_plan_integration():
    """Test plan tool through MCP protocol."""
    async with AsyncClient(app=app) as client:
        response = await client.post("/tools/plan", json={
            "task": "Create user authentication system",
            "repo_context": {"tech_stack": ["Python", "FastAPI"]}
        })

        assert response.status_code == 200
        data = response.json()
        assert "task_breakdown" in data
        assert "affected_files" in data
        assert len(data["task_breakdown"]) > 0
```

### Testing Commands

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test categories
pytest tests/unit/
pytest tests/integration/

# Run tests with Docker containers
pytest --docker-compose-file docker-compose.test.yml

# Performance tests
pytest tests/performance/ --benchmark-only
```

## Pull Request Process

### Before Submitting

1. **Create feature branch** from main
2. **Follow naming convention**: `feature/description`, `fix/issue-number`, `docs/update-readme`
3. **Ensure all tests pass** locally
4. **Run pre-commit hooks**
5. **Update documentation** if needed
6. **Add/update tests** for new functionality

### PR Requirements

#### PR Title Format
```
type(scope): brief description

Examples:
feat(audit): add comprehensive security auditing tool
fix(containers): resolve memory leak in session cleanup
docs(readme): update installation requirements
test(integration): add MCP protocol compliance tests
```

#### PR Description Template
```markdown
## Description
Brief description of changes and motivation.

## Type of Change
- [ ] Bug fix (non-breaking change fixing an issue)
- [ ] New feature (non-breaking change adding functionality)
- [ ] Breaking change (fix or feature causing existing functionality to change)
- [ ] Documentation update

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing completed
- [ ] Performance impact assessed

## Security Considerations
- [ ] Security implications reviewed
- [ ] No sensitive data exposed
- [ ] Authentication/authorization unchanged
- [ ] Container isolation maintained

## Documentation
- [ ] README updated if needed
- [ ] API documentation updated
- [ ] Code comments added for complex logic
- [ ] CHANGELOG updated

## Checklist
- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Tests pass locally
- [ ] No merge conflicts
- [ ] Commits are signed
```

### Review Process

1. **Automated checks** must pass (CI/CD, tests, linting)
2. **Code review** by at least one maintainer
3. **Security review** for security-related changes
4. **Documentation review** for public API changes
5. **Performance review** for performance-critical changes

### Merge Requirements

- **All checks passing**
- **Approved by maintainer**
- **No unresolved conversations**
- **Up-to-date with main branch**
- **Squash and merge** preferred for feature branches

## Issue Guidelines

### Issue Templates

#### Bug Report
```markdown
## Bug Description
Clear description of the bug.

## Steps to Reproduce
1. Step one
2. Step two
3. Expected vs actual behavior

## Environment
- OS: [e.g., Ubuntu 22.04]
- Docker version: [e.g., 24.0.0]
- Python version: [e.g., 3.12.0]
- Server version: [e.g., v1.2.0]

## Logs
```
Relevant log output
```

## Additional Context
Any other relevant information.
```

#### Feature Request
```markdown
## Feature Description
Clear description of the proposed feature.

## Use Case
Why is this feature needed? What problem does it solve?

## Proposed Solution
How should this feature work?

## Alternatives Considered
Other approaches considered.

## Additional Context
Any other relevant information.
```

### Issue Labels

- **Type**: `bug`, `feature`, `enhancement`, `documentation`
- **Priority**: `low`, `medium`, `high`, `critical`
- **Component**: `auth`, `containers`, `mcp`, `security`, `docs`
- **Status**: `needs-triage`, `in-progress`, `blocked`, `ready-for-review`

## Security Considerations

### Security Review Process

All contributions must consider security implications:

1. **Authentication and authorization** changes require security review
2. **Container configuration** changes must maintain isolation
3. **Network security** must be preserved
4. **Credential handling** must follow secure practices
5. **Input validation** must be comprehensive

### Security Guidelines

#### Container Security
```python
# Always use non-root users
CONTAINER_CONFIG = {
    "user": "1000:1000",
    "security_opt": ["no-new-privileges:true"],
    "cap_drop": ["ALL"],
    "read_only": True
}

# Never expose Docker socket without restrictions
# Use minimal required capabilities only
```

#### Input Validation
```python
from pydantic import BaseModel, validator

class ToolRequest(BaseModel):
    message: str
    agent_id: str

    @validator('message')
    def validate_message(cls, v):
        if len(v) > 10000:
            raise ValueError('Message too long')
        return v.strip()

    @validator('agent_id')
    def validate_agent_id(cls, v):
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('Invalid agent ID format')
        return v
```

#### Credential Management
```python
# Never log credentials
logger.info("Authentication attempt", agent_id=agent_id)  # Good
logger.info("Auth with key", api_key=api_key)  # Bad

# Use environment variables or secrets
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable required")
```

### Reporting Security Issues

**Do not open public issues for security vulnerabilities.**

Email security issues to: security@example.com

Include:
- Description of vulnerability
- Steps to reproduce
- Impact assessment
- Suggested fix (if any)

## Documentation Standards

### Documentation Requirements

- **API documentation** for all public methods
- **Usage examples** for complex features
- **Configuration guides** for setup options
- **Troubleshooting guides** for common issues
- **Architecture documentation** for design decisions

### Documentation Format

#### Code Documentation
```python
class ContainerManager:
    """
    Manages Docker containers for Codex CLI agents.

    This class provides complete lifecycle management for agent containers,
    including creation, monitoring, and cleanup. Each agent gets an isolated
    container environment with proper resource limits and security constraints.

    Attributes:
        config: Configuration for container management
        docker_client: Docker client for container operations
        active_containers: Map of agent_id to container instances

    Example:
        >>> config = ContainerConfig(memory="2G", cpu_limit=2.0)
        >>> manager = ContainerManager(config)
        >>> container = await manager.create_agent_container("agent-123")
    """
```

#### README Updates
- Keep installation instructions current
- Update tool descriptions when adding features
- Maintain troubleshooting section
- Update configuration examples

#### Changelog Format
```markdown
## [1.3.0] - 2024-01-15

### Added
- New audit tool with security vulnerability detection
- Chat tool for conversational AI assistance
- Debug tool with intelligent error analysis

### Changed
- Improved timeout handling for all MCP tools
- Enhanced error messages with structured responses

### Fixed
- Container memory leak in long-running sessions
- Authentication token refresh issues

### Security
- Added input validation for all tool parameters
- Improved container isolation with security options
```

## Getting Help

### Community Resources

- **GitHub Discussions**: General questions and ideas
- **GitHub Issues**: Bug reports and feature requests
- **Documentation**: Comprehensive guides and API reference
- **Examples**: Working examples in `/examples` directory

### Development Help

- **Code review**: Request review from maintainers
- **Architecture questions**: Open discussion for design decisions
- **Testing help**: Ask for guidance on testing approaches
- **Security review**: Request security assessment for changes

### Contact

- **General questions**: GitHub Discussions
- **Bug reports**: GitHub Issues
- **Security issues**: security@example.com
- **Maintainers**: @maintainer1, @maintainer2

---

**Thank you for contributing to the Codex CLI MCP Server project!**

Your contributions help make this tool better for the entire AI agent ecosystem.