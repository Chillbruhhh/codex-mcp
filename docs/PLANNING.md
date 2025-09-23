# 🧠 Codex CLI MCP Server - Project Planning

## Project Vision
Create a production-ready Model Context Protocol (MCP) server that wraps OpenAI's Codex CLI, enabling AI agents to interact with Codex through standardized MCP interfaces. Each agent session will spawn an isolated Codex instance in Docker containers for security and resource management.

## Architecture Overview

### Core Components
- **MCP Server**: FastMCP-based server implementing MCP protocol
- **Container Manager**: Docker-based process isolation for Codex CLI instances
- **Session Manager**: Per-agent session handling with lifecycle management
- **Authentication Handler**: Secure credential management for Codex CLI access
- **Subprocess Controller**: Async process management with proper cleanup

### Technology Stack
- **Framework**: FastMCP 2.0 (Python MCP server framework)
- **Language**: Python 3.12+
- **Containerization**: Docker for process isolation
- **Process Management**: asyncio subprocess with context managers
- **Authentication**: Environment variable injection + mounted secrets
- **Configuration**: TOML-based config templates with runtime substitution

## Key Design Decisions

### 1. Process Isolation Strategy
- **Per-agent containers**: Each agent gets isolated Codex CLI instance
- **Ephemeral containers**: Fresh container per session for security
- **Resource limits**: CPU/memory quotas to prevent resource monopolization
- **Network isolation**: Restricted container networking with API-only access

### 2. Authentication Architecture
- **Runtime credential injection**: No baked-in secrets in containers
- **Multiple auth methods**: Support API keys, OAuth, and multi-provider configs
- **Template-based config**: Dynamic TOML generation from environment variables
- **Secure storage**: Read-only mounted secrets with proper file permissions

### 3. Session Management
- **Session isolation**: Separate working directories and state per agent
- **Cleanup policies**: Automatic container removal after session timeout
- **State persistence**: Optional session resumption with mounted volumes
- **Audit logging**: Complete operation tracking for transparency

### 4. MCP Tool Interface
- **Full Codex functionality**: Chat, code generation, file operations, project management
- **Streaming support**: Real-time progress updates for long-running operations
- **Error handling**: Comprehensive error mapping from Codex CLI to MCP responses
- **Resource monitoring**: Usage tracking and quota enforcement

## Technical Constraints

### Performance Requirements
- **Startup time**: Container initialization under 5 seconds
- **Concurrent sessions**: Support 20+ simultaneous agent sessions
- **Resource efficiency**: Minimal overhead per Codex instance
- **Cleanup timing**: Graceful termination within 10 seconds

### Security Requirements
- **Process isolation**: Complete separation between agent sessions
- **Credential security**: No secret exposure in logs or process lists
- **Resource limits**: Prevention of DoS through resource exhaustion
- **Network security**: Minimal container networking surface

### Compatibility Requirements
- **Codex CLI versions**: Support latest stable Codex CLI releases
- **Container platforms**: Docker and Podman compatibility
- **MCP protocol**: Full MCP 1.0 specification compliance
- **Python versions**: 3.12+ with asyncio subprocess support

## File Structure
```
codex-mcp-server/
├── README.md                 # Project overview and setup
├── PLANNING.md              # This document
├── TASK.md                  # Current tasks and backlog
├── requirements.txt         # Python dependencies
├── Dockerfile              # Container definition
├── docker-compose.yml      # Development environment
├── server.py               # Main MCP server entry point
├── src/
│   ├── __init__.py
│   ├── mcp_server.py       # FastMCP server implementation
│   ├── container_manager.py # Docker container lifecycle
│   ├── session_manager.py  # Agent session handling
│   ├── auth_manager.py     # Authentication and config
│   ├── subprocess_pool.py  # Process management
│   └── utils/
│       ├── __init__.py
│       ├── config.py       # Configuration management
│       └── logging.py      # Structured logging
├── tests/
│   ├── __init__.py
│   ├── test_mcp_server.py
│   ├── test_container_manager.py
│   ├── test_session_manager.py
│   └── test_auth_manager.py
├── config/
│   ├── codex-config.toml.template
│   └── docker-compose.env.template
└── docs/
    ├── installation.md
    ├── configuration.md
    └── api-reference.md
```

## Development Phases

### Phase 1: Core MCP Server (Week 1)
- FastMCP server setup with basic tool definitions
- Container manager with Docker API integration
- Simple session management without persistence
- Basic authentication with API key support

### Phase 2: Advanced Features (Week 2)
- Full Codex CLI tool coverage (chat, code, files, projects)
- Streaming operation support with progress reporting
- Enhanced session management with cleanup policies
- OAuth authentication support

### Phase 3: Production Hardening (Week 3)
- Comprehensive error handling and recovery
- Resource monitoring and quota enforcement
- Security hardening and vulnerability assessment
- Performance optimization and load testing

### Phase 4: Deployment & Documentation (Week 4)
- Production Docker images and deployment configs
- Comprehensive documentation and examples
- Integration testing with various AI agents
- Community release preparation

## Quality Standards

### Code Quality
- **Test Coverage**: Minimum 80% unit test coverage
- **Type Safety**: Full type hints with mypy validation
- **Code Style**: Black formatting with flake8 linting
- **Documentation**: Google-style docstrings for all functions

### Operational Quality
- **Monitoring**: Structured logging with correlation IDs
- **Health Checks**: Container and service health endpoints
- **Error Handling**: Graceful degradation and recovery
- **Performance**: Sub-second response times for MCP calls

## Dependencies

### Core Dependencies
- `fastmcp`: MCP server framework
- `docker`: Container management
- `asyncio`: Async subprocess handling
- `pydantic`: Data validation and serialization
- `tomli/tomli-w`: TOML configuration handling

### Development Dependencies
- `pytest`: Unit testing framework
- `pytest-asyncio`: Async test support
- `pytest-docker`: Docker integration testing
- `black`: Code formatting
- `mypy`: Type checking
- `flake8`: Linting

### System Dependencies
- Docker Engine 20.10+
- Python 3.12+
- Codex CLI (installed in container)

## Risk Mitigation

### Security Risks
- **Credential exposure**: Runtime injection + read-only mounts
- **Container escape**: Non-root execution + capability restrictions
- **Resource exhaustion**: Process limits + monitoring + cleanup

### Operational Risks
- **Container failures**: Health checks + automatic restart policies
- **Memory leaks**: Proper cleanup + resource monitoring
- **Network issues**: Retry logic + timeout handling

### Development Risks
- **Codex CLI API changes**: Version pinning + compatibility testing
- **FastMCP updates**: Dependency versioning + integration tests
- **Docker compatibility**: Multi-platform testing + standardized images