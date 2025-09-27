"""
Docker container manager for Codex CLI integration.

This module handles the creation, lifecycle management, and cleanup of Docker
containers that run isolated Codex CLI instances for each agent session.
Implements security best practices including resource limits, network isolation,
and credential injection.
"""

import asyncio
import json
import os
import tempfile
import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, AsyncContextManager
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import docker
from docker.errors import DockerException, NotFound, APIError
import structlog

from .utils.config import Config, get_config
from .utils.logging import LogContext, set_correlation_id
from .auth_manager import CodexAuthManager, AuthMethod
from .persistence import AgentPersistenceManager, ContainerStatus
from .interactive_codex_manager import InteractiveCodexManager
from .persistent_agent_manager import PersistentAgentManager
from .async_docker_manager import AsyncDockerManager

logger = structlog.get_logger(__name__)


@dataclass
class ContainerSession:
    """Represents a Codex CLI container session with persistent conversation."""
    session_id: str
    agent_id: str
    container_id: Optional[str] = None
    container_name: str = ""
    created_at: float = field(default_factory=time.time)
    status: str = "initializing"
    config_dir: Optional[str] = None
    workspace_dir: Optional[str] = None
    client_workspace_dir: Optional[str] = None  # Real workspace path from MCP client
    environment: Dict[str, str] = field(default_factory=dict)
    resource_limits: Dict[str, Any] = field(default_factory=dict)

    # New fields for persistent conversation
    codex_exec_id: Optional[str] = None  # Docker exec instance ID
    codex_socket: Optional[Any] = None   # Docker socket for communication
    conversation_active: bool = False
    auth_setup_complete: bool = False
    last_interaction: float = field(default_factory=time.time)

    # Configuration fields
    model: str = "gpt-5-codex"
    reasoning: str = "medium"

    # Cleanup coordination fields
    cleanup_in_progress: bool = False
    cleanup_completed: bool = False
    cleanup_lock: Optional[asyncio.Lock] = field(default_factory=lambda: asyncio.Lock())
    cleanup_error: Optional[str] = None


class ContainerError(Exception):
    """Base exception for container operations."""
    pass


class ContainerCreationError(ContainerError):
    """Raised when container creation fails."""
    pass


class ContainerExecutionError(ContainerError):
    """Raised when container command execution fails."""
    pass


class CodexContainerManager:
    """
    Manages Docker containers for Codex CLI instances.

    Provides complete lifecycle management including creation, configuration,
    execution, monitoring, and cleanup of isolated Codex CLI containers.
    """

    def __init__(self, config: Optional[Config] = None, data_path: str = "./data"):
        """
        Initialize the container manager.

        Args:
            config: Optional configuration object, loads default if not provided
            data_path: Path to persistent data directory
        """
        self.config = config or get_config()
        self.docker_client = docker.from_env()
        self.async_docker = AsyncDockerManager(self.docker_client, self.config.server.timeouts)
        self.auth_manager = CodexAuthManager(self.config)
        self.persistence_manager = AgentPersistenceManager(data_path)
        self.interactive_manager = InteractiveCodexManager(self.config)
        self.persistent_agent_manager = PersistentAgentManager(self.docker_client, self.config)
        self.active_sessions: Dict[str, ContainerSession] = {}
        self.base_image = "codex-mcp-base"
        self._oauth_tokens: Optional[Dict[str, Any]] = None
        self._interactive_bridge_script: Optional[str] = None

        # Check for persistent mode
        self.persistent_mode = os.getenv("PERSISTENT_MODE", "false").lower() == "true"

        logger.info("Container manager initialized",
                   max_sessions=self.config.server.max_concurrent_sessions,
                   persistent_mode=self.persistent_mode,
                   data_path=data_path)

    async def ensure_base_image(self) -> str:
        """
        Ensure the Codex CLI base image exists, building if necessary.

        Returns:
            str: The base image name/tag
        """
        try:
            # Check if base image exists (async)
            await self.async_docker.get_image(self.base_image)
            logger.info("Base image found", image=self.base_image)
            return self.base_image
        except NotFound:
            logger.info("Base image not found, building...", image=self.base_image)
            return await self._build_base_image()

    async def _build_base_image(self) -> str:
        """Build the Codex CLI base image."""
        dockerfile_content = self._generate_dockerfile()

        # Create temporary directory for build context
        with tempfile.TemporaryDirectory() as temp_dir:
            dockerfile_path = Path(temp_dir) / "Dockerfile"
            dockerfile_path.write_text(dockerfile_content)

            try:
                # Build image asynchronously
                image, build_logs = await self.async_docker.build_image(
                    path=temp_dir,
                    tag=self.base_image,
                    rm=True,
                    nocache=False
                )

                logger.info("Base image built successfully",
                           image=self.base_image,
                           image_id=image.id[:12])
                return self.base_image

            except Exception as e:
                logger.error("Failed to build base image", error=str(e))
                raise ContainerCreationError(f"Failed to build base image: {e}")

    def _generate_dockerfile(self) -> str:
        """Generate Dockerfile content for Codex CLI base image."""
        return """
# Codex CLI Base Image for MCP Server
FROM node:20-alpine

# Install system dependencies
RUN apk add --no-cache \\
    git \\
    curl \\
    python3 \\
    py3-pip \\
    bash

# Install Codex CLI globally
RUN npm install -g @openai/codex

# Create non-root user for security (Alpine Linux syntax)
RUN addgroup -g 1001 codex && \\
    adduser -D -u 1001 -G codex codex

# Create directories
RUN mkdir -p /app/workspace /app/config /app/sessions && \\
    chown -R codex:codex /app

# Create logging startup script - using echo commands for better compatibility
RUN echo '#!/bin/bash' > /app/logging_startup.sh && \\
    echo '# Agent Container Logging Startup Script' >> /app/logging_startup.sh && \\
    echo 'echo "=== CODEX AGENT CONTAINER STARTUP ==="' >> /app/logging_startup.sh && \\
    echo 'echo "Timestamp: $(date)"' >> /app/logging_startup.sh && \\
    echo 'echo "Agent ID: ${AGENT_ID:-unknown}"' >> /app/logging_startup.sh && \\
    echo 'echo "Session ID: ${SESSION_ID:-unknown}"' >> /app/logging_startup.sh && \\
    echo 'echo "Container ID: $(hostname)"' >> /app/logging_startup.sh && \\
    echo 'echo "Working Directory: $(pwd)"' >> /app/logging_startup.sh && \\
    echo 'echo "User: $(whoami)"' >> /app/logging_startup.sh && \\
    echo 'echo "====================================="' >> /app/logging_startup.sh && \\
    echo '' >> /app/logging_startup.sh && \\
    echo '# Check if Codex CLI is available' >> /app/logging_startup.sh && \\
    echo 'echo "Checking Codex CLI availability..."' >> /app/logging_startup.sh && \\
    echo 'if command -v codex &> /dev/null; then' >> /app/logging_startup.sh && \\
    echo '    echo "✓ Codex CLI is available at: $(which codex)"' >> /app/logging_startup.sh && \\
    echo '    echo "✓ Codex CLI version: $(codex --version 2>&1 || echo '"'"'Version check failed'"'"')"' >> /app/logging_startup.sh && \\
    echo 'else' >> /app/logging_startup.sh && \\
    echo '    echo "✗ Codex CLI not found in PATH"' >> /app/logging_startup.sh && \\
    echo '    echo "PATH: $PATH"' >> /app/logging_startup.sh && \\
    echo 'fi' >> /app/logging_startup.sh && \\
    echo '' >> /app/logging_startup.sh && \\
    echo '# Check environment variables' >> /app/logging_startup.sh && \\
    echo 'echo "Environment check:"' >> /app/logging_startup.sh && \\
    echo 'echo "- OPENAI_API_KEY: ${OPENAI_API_KEY:+SET (${#OPENAI_API_KEY} chars)}${OPENAI_API_KEY:-NOT SET}"' >> /app/logging_startup.sh && \\
    echo 'echo "- CODEX_MODEL: ${CODEX_MODEL:-not set}"' >> /app/logging_startup.sh && \\
    echo 'echo "- AGENT_ID: ${AGENT_ID:-not set}"' >> /app/logging_startup.sh && \\
    echo 'echo "- SESSION_ID: ${SESSION_ID:-not set}"' >> /app/logging_startup.sh && \\
    echo '' >> /app/logging_startup.sh && \\
    echo '# Check mounted volumes' >> /app/logging_startup.sh && \\
    echo 'echo "Volume mounts:"' >> /app/logging_startup.sh && \\
    echo 'ls -la /app/config/ 2>/dev/null && echo "✓ Config directory mounted" || echo "✗ Config directory not found"' >> /app/logging_startup.sh && \\
    echo 'ls -la /app/workspace/ 2>/dev/null && echo "✓ Workspace directory mounted" || echo "✗ Workspace directory not found"' >> /app/logging_startup.sh && \\
    echo '' >> /app/logging_startup.sh && \\
    echo 'echo "====================================="' >> /app/logging_startup.sh && \\
    echo 'echo "Container is ready for Codex commands"' >> /app/logging_startup.sh && \\
    echo 'echo "Waiting for commands... (logging all activity)"' >> /app/logging_startup.sh && \\
    echo 'echo "====================================="' >> /app/logging_startup.sh && \\
    echo '' >> /app/logging_startup.sh && \\
    echo '# Create a named pipe for command logging' >> /app/logging_startup.sh && \\
    echo 'mkfifo /tmp/command_log 2>/dev/null || true' >> /app/logging_startup.sh && \\
    echo '' >> /app/logging_startup.sh && \\
    echo '# Function to log activity with timestamps' >> /app/logging_startup.sh && \\
    echo 'log_activity() {' >> /app/logging_startup.sh && \\
    echo '    while IFS= read -r line; do' >> /app/logging_startup.sh && \\
    echo '        echo "[$(date '"'"'+%Y-%m-%d %H:%M:%S'"'"')] $line"' >> /app/logging_startup.sh && \\
    echo '    done' >> /app/logging_startup.sh && \\
    echo '}' >> /app/logging_startup.sh && \\
    echo '' >> /app/logging_startup.sh && \\
    echo '# Start background process to monitor the command log' >> /app/logging_startup.sh && \\
    echo 'tail -f /tmp/command_log 2>/dev/null | log_activity &' >> /app/logging_startup.sh && \\
    echo '' >> /app/logging_startup.sh && \\
    echo '# Log periodic heartbeats' >> /app/logging_startup.sh && \\
    echo 'while true; do' >> /app/logging_startup.sh && \\
    echo '    sleep 300  # 5 minutes' >> /app/logging_startup.sh && \\
    echo '    echo "[$(date '"'"'+%Y-%m-%d %H:%M:%S'"'"')] Heartbeat: Container still active (uptime: $(uptime -p))"' >> /app/logging_startup.sh && \\
    echo 'done | log_activity &' >> /app/logging_startup.sh && \\
    echo '' >> /app/logging_startup.sh && \\
    echo '# Keep the container running and responsive' >> /app/logging_startup.sh && \\
    echo 'exec tail -f /dev/null' >> /app/logging_startup.sh && \\
    chmod +x /app/logging_startup.sh && \\
    chown codex:codex /app/logging_startup.sh

# Switch to non-root user
USER codex
WORKDIR /app

# Set up PATH to include Codex CLI
ENV PATH="/usr/local/bin:$PATH"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
    CMD codex --version || exit 1

# Default command (will be overridden)
CMD ["bash", "/app/logging_startup.sh"]
"""

    @asynccontextmanager
    async def create_session(
        self,
        session_id: str,
        agent_id: str,
        model: str = "gpt-5-codex",
        provider: str = "openai",
        approval_mode: str = "suggest",
        reasoning: str = "medium",
        client_workspace_dir: Optional[str] = None
    ) -> AsyncContextManager[ContainerSession]:
        """
        Create and manage a Codex CLI container session.

        Args:
            session_id: Unique session identifier
            agent_id: Agent identifier
            model: Codex model to use
            provider: AI provider (openai, azure, etc.)
            approval_mode: Codex approval mode
            reasoning: Reasoning level for GPT-5 models (low, medium, high)
            client_workspace_dir: Client's actual workspace directory for direct collaboration

        Yields:
            ContainerSession: Active container session

        Raises:
            ContainerCreationError: If container creation fails
        """
        with LogContext(session_id):
            logger.info("Creating container session",
                       session_id=session_id,
                       agent_id=agent_id)

            # Check session limits
            if len(self.active_sessions) >= self.config.server.max_concurrent_sessions:
                raise ContainerCreationError(
                    f"Maximum sessions ({self.config.server.max_concurrent_sessions}) reached"
                )

            session = ContainerSession(
                session_id=session_id,
                agent_id=agent_id,
                container_name=f"codex-{session_id}",
                status="creating",
                model=model,
                reasoning=reasoning,
                client_workspace_dir=client_workspace_dir  # Store client workspace for mounting
            )

            try:
                # Ensure base image exists
                await self.ensure_base_image()

                # Create session directories
                await self._create_session_directories(session)

                # Generate Codex CLI configuration
                await self._generate_codex_config(session, model, provider, approval_mode, reasoning)

                # Create container
                await self._create_container(session)

                # Start container
                await self._start_container(session)

                # Start interactive Codex CLI session
                await self._start_interactive_codex_session(session)

                # Add to active sessions
                self.active_sessions[session_id] = session
                session.status = "active"

                logger.info("Container session created successfully",
                           session_id=session_id,
                           container_id=session.container_id)

                yield session

            except Exception as e:
                logger.error("Failed to create container session",
                           session_id=session_id,
                           error=str(e))
                # Cleanup on failure
                await self._cleanup_session(session)
                raise

            finally:
                # Cleanup when context exits (only if not already cleaned up)
                if session_id in self.active_sessions:
                    session = self.active_sessions[session_id]

                    # Check if cleanup is already completed to avoid race conditions
                    if not getattr(session, 'cleanup_completed', False):
                        await self._cleanup_session(session)

                    # Remove from active sessions tracking
                    if session_id in self.active_sessions:
                        del self.active_sessions[session_id]

                # Clear auth manager session credentials
                self.auth_manager.clear_session_credentials(session_id)

    async def get_or_create_persistent_agent_container(
        self,
        agent_id: str,
        model: str = "gpt-5-codex",
        provider: str = "openai",
        approval_mode: str = "suggest",
        reasoning: str = "medium"
    ) -> ContainerSession:
        """
        Get existing or create new persistent container for an agent.

        This is the main entry point for the persistent agent architecture.
        It checks if the agent already has a running container and reuses it,
        or creates a new one if needed.

        Args:
            agent_id: Unique agent identifier
            model: Codex model to use
            provider: AI provider
            approval_mode: Codex approval mode

        Returns:
            ContainerSession: Active container session for the agent

        Raises:
            ContainerCreationError: If container operations fail
        """
        with LogContext(agent_id):
            logger.info("Getting or creating persistent agent container",
                       agent_id=agent_id,
                       persistent_mode=self.persistent_mode)

            # Check if agent already has a container
            existing_info = await self.persistence_manager.get_agent_container(agent_id)

            if existing_info:
                logger.info("Found existing agent container",
                           agent_id=agent_id,
                           container_id=existing_info.container_id[:12])

                # Try to reconnect to existing container
                try:
                    session = await self._reconnect_to_agent_container(existing_info)
                    logger.info("Successfully reconnected to agent container",
                               agent_id=agent_id,
                               container_id=session.container_id[:12])
                    return session

                except Exception as e:
                    logger.warning("Failed to reconnect to existing container, creating new one",
                                 agent_id=agent_id,
                                 error=str(e))
                    # Remove stale entry and create new container
                    await self.persistence_manager.remove_agent_container(agent_id)

            # Create new persistent container for agent
            logger.info("Creating new persistent container for agent",
                       agent_id=agent_id)

            session = await self._create_new_persistent_agent_container(
                agent_id=agent_id,
                model=model,
                provider=provider,
                approval_mode=approval_mode,
                reasoning=reasoning
            )

            logger.info("Persistent agent container ready",
                       agent_id=agent_id,
                       container_id=session.container_id[:12])

            return session

    async def _reconnect_to_agent_container(self, agent_info) -> ContainerSession:
        """
        Reconnect to an existing agent container.

        Args:
            agent_info: AgentContainerInfo from persistence manager

        Returns:
            ContainerSession: Reconnected session

        Raises:
            ContainerCreationError: If reconnection fails
        """
        try:
            # Check if container still exists and is running
            container = self.docker_client.containers.get(agent_info.container_id)

            if container.status != "running":
                # Try to start the container if it's stopped
                container.start()

                # Wait for container to be running
                max_wait = 30
                wait_time = 0
                while wait_time < max_wait:
                    container.reload()
                    if container.status == "running":
                        break
                    await asyncio.sleep(1)
                    wait_time += 1

                if container.status != "running":
                    raise ContainerCreationError(
                        f"Failed to start existing container within {max_wait} seconds"
                    )

            # Create session object for existing container
            persistent_session_id = agent_info.persistent_session_id or (
                f"persistent-{agent_info.agent_id}"
            )
            if agent_info.persistent_session_id is None:
                await self.persistence_manager.update_persistent_session_id(
                    agent_info.agent_id,
                    persistent_session_id,
                )

            session_id = persistent_session_id
            session = ContainerSession(
                session_id=session_id,
                agent_id=agent_info.agent_id,
                container_id=agent_info.container_id,
                container_name=agent_info.container_name,
                config_dir=agent_info.config_path,
                workspace_dir=agent_info.workspace_path,
                conversation_active=True,
                auth_setup_complete=True,  # Assume auth is already set up
                model=getattr(agent_info, 'model', 'gpt-5-codex'),  # Use stored or default
                reasoning=getattr(agent_info, 'reasoning', 'medium')  # Use stored or default
            )

            # Update persistence manager
            await self.persistence_manager.update_container_status(
                agent_info.agent_id,
                ContainerStatus.RUNNING
            )
            await self.persistence_manager.update_last_active(agent_info.agent_id)

            # Add to active sessions
            self.active_sessions[session_id] = session

            logger.info("Successfully reconnected to agent container",
                       agent_id=agent_info.agent_id,
                       container_id=agent_info.container_id[:12])

            return session

        except NotFound:
            # Container no longer exists
            await self.persistence_manager.remove_agent_container(agent_info.agent_id)
            raise ContainerCreationError(f"Container {agent_info.container_id[:12]} no longer exists")

        except Exception as e:
            logger.error("Failed to reconnect to agent container",
                        agent_id=agent_info.agent_id,
                        container_id=agent_info.container_id[:12],
                        error=str(e))
            raise ContainerCreationError(f"Reconnection failed: {e}")

    async def _create_new_persistent_agent_container(
        self,
        agent_id: str,
        model: str = "gpt-5-codex",
        provider: str = "openai",
        approval_mode: str = "suggest",
        reasoning: str = "medium"
    ) -> ContainerSession:
        """
        Create a new persistent container for an agent.

        Args:
            agent_id: Agent identifier
            model: Codex model to use
            provider: AI provider
            approval_mode: Codex approval mode
            reasoning: Reasoning level for GPT-5 models (low, medium, high)

        Returns:
            ContainerSession: New container session

        Raises:
            ContainerCreationError: If creation fails
        """
        session_id = f"persistent-{agent_id}-{int(time.time())}"

        # Create persistent workspace and config directories
        agent_data_path = Path(self.persistence_manager.data_path) / "agents" / agent_id
        agent_data_path.mkdir(parents=True, exist_ok=True)

        workspace_dir = str(agent_data_path / "workspace")
        config_dir = str(agent_data_path / "config")

        Path(workspace_dir).mkdir(exist_ok=True)
        Path(config_dir).mkdir(exist_ok=True)

        session = ContainerSession(
            session_id=session_id,
            agent_id=agent_id,
            container_name=f"codex-agent-{agent_id}",
            config_dir=config_dir,
            workspace_dir=workspace_dir,
            status="creating",
            model=model,
            reasoning=reasoning
        )

        try:
            # Ensure base image exists
            await self.ensure_base_image()

            # Generate Codex CLI configuration
            await self._generate_codex_config(session, model, provider, approval_mode, reasoning)

            # Create and start container
            await self._create_container(session)
            await self._start_container(session)

            # Mark conversation as ready (auth setup will happen on first message)
            session.conversation_active = True

            # Register with persistence manager
            await self.persistence_manager.register_agent_container(
                agent_id=agent_id,
                container_id=session.container_id,
                container_name=session.container_name,
                workspace_path=workspace_dir,
                config_path=config_dir,
                model=model,
                reasoning=reasoning,
                provider=provider,
                approval_mode=approval_mode,
                persistent_session_id=session.session_id
            )

            # Update status to running
            await self.persistence_manager.update_container_status(
                agent_id,
                ContainerStatus.RUNNING
            )

            # Add to active sessions
            self.active_sessions[session_id] = session

            logger.info("New persistent agent container created",
                       agent_id=agent_id,
                       container_id=session.container_id[:12])

            return session

        except Exception as e:
            logger.error("Failed to create persistent agent container",
                        agent_id=agent_id,
                        error=str(e))
            # Cleanup on failure
            await self._cleanup_session(session)
            raise

    async def _create_persistent_session(
        self,
        session_id: str,
        agent_id: str,
        model: str = "gpt-5-codex",
        provider: str = "openai",
        approval_mode: str = "suggest",
        reasoning: str = "medium",
        client_workspace_dir: Optional[str] = None
    ) -> ContainerSession:
        """
        Create a persistent container session that doesn't auto-cleanup.

        This method creates a container session without using context managers,
        making it suitable for persistent sessions that need manual cleanup.

        Args:
            session_id: Unique session identifier
            agent_id: Agent identifier for this session
            model: Codex model configuration
            provider: AI provider configuration
            approval_mode: Codex approval mode
            reasoning: Reasoning level for GPT-5 models (low, medium, high)

        Returns:
            ContainerSession: Active container session

        Raises:
            ContainerCreationError: If container creation fails
        """
        with LogContext(session_id):
            logger.info("Creating persistent container session",
                       session_id=session_id,
                       agent_id=agent_id)

            # Create session object
            session = ContainerSession(
                session_id=session_id,
                agent_id=agent_id,
                container_name=f"codex-session-{agent_id}-{int(time.time())}",
                model=model,
                reasoning=reasoning,
                client_workspace_dir=client_workspace_dir  # Store client workspace
            )

            try:
                # Ensure base image exists
                await self.ensure_base_image()

                # Create session directories
                await self._create_session_directories(session)

                # Generate Codex CLI configuration
                await self._generate_codex_config(session, model, provider, approval_mode, reasoning)

                # Create and start container
                await self._create_container(session)
                await self._start_container(session)

                # Mark conversation as ready (auth setup will happen on first message)
                session.conversation_active = True

                # Register session for tracking
                self.active_sessions[session_id] = session

                logger.info("Persistent container session created successfully",
                           session_id=session_id,
                           container_id=session.container_id[:12])

                return session

            except Exception as e:
                logger.error("Failed to create persistent container session",
                           session_id=session_id,
                           error=str(e))
                # Cleanup on failure
                await self._cleanup_session(session)
                raise

    async def _create_session_directories(self, session: ContainerSession) -> None:
        """Create temporary directories for session."""
        # Create config directory
        config_dir = tempfile.mkdtemp(prefix=f"codex-config-{session.session_id}-")
        session.config_dir = config_dir

        # Create workspace directory
        workspace_dir = tempfile.mkdtemp(prefix=f"codex-workspace-{session.session_id}-")
        session.workspace_dir = workspace_dir

        logger.debug("Session directories created",
                    config_dir=config_dir,
                    workspace_dir=workspace_dir)

    async def _generate_codex_config(
        self,
        session: ContainerSession,
        model: str,
        provider: str,
        approval_mode: str,
        reasoning: str
    ) -> None:
        """Generate Codex CLI configuration for the session using auth manager."""
        # Get session credentials using configured authentication preferences
        credentials = await self.auth_manager.get_session_credentials(
            session.session_id
        )

        # Generate config using auth manager
        config_content = self.auth_manager.generate_codex_config(
            credentials=credentials,
            model=model,
            approval_mode=approval_mode,
            reasoning=reasoning
        )

        config_path = Path(session.config_dir) / "config.toml"
        config_path.write_text(config_content)

        # Create auth.json file for Codex CLI authentication
        # This is required for Codex CLI to properly authenticate with the API
        tokens_payload = None

        if credentials.method == AuthMethod.CHATGPT_OAUTH:
            if credentials.oauth_tokens:
                tokens_payload = credentials.oauth_tokens.to_dict()
            elif credentials.environment_vars.get("OPENAI_ACCESS_TOKEN"):
                tokens_payload = {
                    "access_token": credentials.environment_vars["OPENAI_ACCESS_TOKEN"],
                    "token_type": "Bearer"
                }

        auth_json_content = {
            "OPENAI_API_KEY": credentials.api_key if credentials.method == AuthMethod.API_KEY else None,
            "tokens": tokens_payload,
            "last_refresh": time.time() if tokens_payload else None
        }
        auth_json_path = Path(session.config_dir) / "auth.json"
        auth_json_path.write_text(json.dumps(auth_json_content))

        logger.debug("Codex config and auth generated",
                    config_path=str(config_path),
                    auth_path=str(auth_json_path),
                    model=model,
                    auth_method=credentials.method.value)

    async def _prepare_persistent_workspace(self, session: ContainerSession) -> str:
        """Ensure a persistent workspace directory exists for the agent."""
        if session.client_workspace_dir and os.path.isdir(session.client_workspace_dir):
            return session.client_workspace_dir

        agent_base = Path(self.persistence_manager.data_path) / "agents" / session.agent_id
        workspace_path = agent_base / "workspace"
        workspace_path.mkdir(parents=True, exist_ok=True)

        if session.workspace_dir and os.path.isdir(session.workspace_dir):
            self._copy_directory_contents(Path(session.workspace_dir), workspace_path)

        return str(workspace_path)

    async def _prepare_persistent_config(self, session: ContainerSession) -> str:
        """Ensure a persistent config directory exists for the agent."""
        agent_base = Path(self.persistence_manager.data_path) / "agents" / session.agent_id
        config_path = agent_base / "config"
        config_path.mkdir(parents=True, exist_ok=True)

        if session.config_dir and os.path.isdir(session.config_dir):
            self._copy_directory_contents(Path(session.config_dir), config_path)

        return str(config_path)

    def _copy_directory_contents(self, source: Path, destination: Path) -> None:
        """Copy directory contents from source to destination, overwriting existing files."""
        if not source.exists():
            return

        try:
            if source.resolve() == destination.resolve():
                return
        except Exception:
            # If resolution fails (e.g., due to permissions), fall back to direct comparison
            if str(source) == str(destination):
                return

        for item in source.iterdir():
            dest_item = destination / item.name
            if item.is_dir():
                shutil.copytree(item, dest_item, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest_item)

    def _get_interactive_bridge_script(self) -> str:
        """Load and cache the interactive Codex bridge script content."""
        if self._interactive_bridge_script is None:
            script_path = Path(__file__).resolve().parent.parent / "scripts" / "interactive_codex_agent.py"
            try:
                self._interactive_bridge_script = script_path.read_text()
            except Exception as exc:
                logger.error(
                    "Failed to load interactive bridge script",
                    error=str(exc),
                    script_path=str(script_path)
                )
                self._interactive_bridge_script = "print('Interactive Codex bridge script missing.')"

        return self._interactive_bridge_script

    async def _create_container(self, session: ContainerSession) -> None:
        """Create the Docker container for the session."""
        try:
            # Get authentication credentials for this session using configured preferences
            credentials = await self.auth_manager.get_session_credentials(
                session.session_id
            )

            # Prepare environment variables using auth manager
            environment = self.auth_manager.get_container_environment(credentials)
            session.environment = environment

            # Resource limits - use more generous limits for debugging
            resource_limits = {
                "mem_limit": self.config.container.memory_limit,
                "memswap_limit": "-1",  # Allow swap usage
                "cpu_period": 100000,
                "cpu_quota": int(float(self.config.container.cpu_limit) * 100000),
                "oom_kill_disable": True  # Disable OOM killer to prevent SIGKILL
            }
            session.resource_limits = resource_limits

            # Create persistent container with long-running command
            # Use tail -f /dev/null to keep container alive indefinitely
            # Convert paths to absolute paths for Docker volume mounting
            abs_config_dir = os.path.abspath(session.config_dir)
            abs_workspace_dir = os.path.abspath(session.workspace_dir)

            # Prepare volume mounts
            volume_mounts = {
                abs_config_dir: {"bind": "/app/config", "mode": "ro"},
                abs_workspace_dir: {"bind": "/app/workspace", "mode": "rw"}
            }

            # Add OAuth token directory mount if OAuth tokens are available and API key not used
            oauth_dir = None
            if credentials.method != AuthMethod.API_KEY:
                oauth_dir = self._get_oauth_directory()
                if oauth_dir and os.path.exists(oauth_dir):
                    abs_oauth_dir = os.path.abspath(oauth_dir)
                    volume_mounts[abs_oauth_dir] = {"bind": "/app/.codex", "mode": "ro"}
                    logger.debug("Adding OAuth token directory mount",
                               host_path=abs_oauth_dir,
                               container_path="/app/.codex")

            container = self.docker_client.containers.create(
                image=self.base_image,
                name=session.container_name,
                environment=environment,
                volumes=volume_mounts,
                working_dir="/app/workspace",
                user="codex",
                network_mode=self.config.container.network_mode,
                auto_remove=False,  # Disable auto_remove for persistent containers
                detach=True,
                stdin_open=True,
                tty=True,
                command=["bash", "/app/logging_startup.sh"],  # Keep container running with logging
                **resource_limits
            )

            session.container_id = container.id
            logger.info("Container created",
                       container_id=container.id[:12],
                       container_name=session.container_name)

        except Exception as e:
            logger.error("Container creation failed", error=str(e))
            raise ContainerCreationError(f"Failed to create container: {e}")

    async def _start_container(self, session: ContainerSession) -> None:
        """Start the container and verify it's running."""
        try:
            container = self.docker_client.containers.get(session.container_id)
            container.start()

            # Wait for container to be running
            max_wait = 30  # seconds
            wait_time = 0
            while wait_time < max_wait:
                container.reload()
                if container.status == "running":
                    break
                await asyncio.sleep(1)
                wait_time += 1

            if container.status != "running":
                raise ContainerCreationError(
                    f"Container failed to start within {max_wait} seconds"
                )

            logger.info("Container started successfully",
                       container_id=session.container_id[:12])

        except Exception as e:
            logger.error("Container start failed", error=str(e))
            raise ContainerCreationError(f"Failed to start container: {e}")

    async def _start_interactive_codex_session(self, session: ContainerSession) -> None:
        """
        Start an interactive Codex CLI session using the InteractiveCodexManager.

        This replaces the old command-based approach with a truly interactive
        conversation-based collaboration system.
        """
        with LogContext(session.session_id):
            try:
                container = self.docker_client.containers.get(session.container_id)

                logger.info("Starting interactive Codex CLI session",
                           container_id=session.container_id[:12],
                           has_client_workspace=session.client_workspace_dir is not None)

                # Setup authentication first
                if not session.auth_setup_complete:
                    await self._setup_codex_auth(container, session)

                # Use the InteractiveCodexManager to start the session
                interactive_session = await self.interactive_manager.start_interactive_session(
                    container=container,
                    session_id=session.session_id,
                    agent_id=session.agent_id,
                    workspace_dir="/app/workspace",
                    client_workspace_dir=session.client_workspace_dir
                )

                # Store the interactive session reference in our container session
                session.conversation_active = True
                session.last_interaction = time.time()

                logger.info("Interactive Codex CLI session started successfully",
                           session_id=session.session_id,
                           agent_id=session.agent_id)

            except Exception as e:
                logger.error("Failed to start interactive Codex CLI session",
                           session_id=session.session_id,
                           error=str(e))
                raise ContainerExecutionError(f"Interactive session startup failed: {e}")


    async def start_codex_conversation(self, session: ContainerSession) -> None:
        """
        Start a persistent Codex CLI conversation session.

        This method implements the working authentication approach:
        1. Sets up auth.json file in the container
        2. Starts Codex CLI in interactive mode
        3. Maintains persistent connection for real-time communication

        Args:
            session: Container session to start conversation in

        Raises:
            ContainerExecutionError: If conversation startup fails
        """
        with LogContext(session.session_id):
            try:
                container = self.docker_client.containers.get(session.container_id)

                logger.info("Starting persistent Codex conversation",
                           container_id=session.container_id[:12])

                # Step 1: Setup authentication first (this was the missing piece!)
                if not session.auth_setup_complete:
                    await self._setup_codex_auth(container, session)

                # Step 2: Start Codex CLI in interactive mode
                # Use the working approach we confirmed manually
                exec_instance = container.exec_run(
                    cmd=["codex"],  # Start interactive Codex CLI
                    stdin=True,
                    stdout=True,
                    stderr=True,
                    tty=True,  # Essential for interactive mode
                    user="codex",
                    workdir="/app/workspace",
                    environment=session.environment,
                    detach=True,  # Keep running in background
                    socket=True   # Get socket for real-time I/O
                )

                # Store the exec details for persistent communication
                session.codex_exec_id = exec_instance.id if hasattr(exec_instance, 'id') else None
                session.codex_socket = exec_instance.output if hasattr(exec_instance, 'output') else exec_instance
                session.conversation_active = True
                session.last_interaction = time.time()

                logger.info("Codex conversation started successfully",
                           session_id=session.session_id)

            except Exception as e:
                logger.error("Failed to start Codex conversation", error=str(e))
                raise ContainerExecutionError(f"Conversation startup failed: {e}")

    async def _setup_codex_auth(self, container, session: ContainerSession) -> None:
        """
        Setup Codex CLI authentication in the container.

        Handles both OAuth tokens (if mounted) and API key authentication.
        """
        try:
            # Check if we have OAuth tokens stored from the main container
            if hasattr(self, '_oauth_tokens') and self._oauth_tokens:
                logger.info("Using stored OAuth tokens from main container", session_id=session.session_id)

                if self._oauth_tokens.get("tokens") and self._oauth_tokens["tokens"].get("access_token"):
                    logger.info("✅ Injecting OAuth tokens for ChatGPT subscription authentication",
                               session_id=session.session_id,
                               access_token_preview=self._oauth_tokens["tokens"]["access_token"][:20] + "...")

                    # Create OAuth auth file in agent container
                    auth_json = json.dumps(self._oauth_tokens)
                    auth_setup_cmd = f'mkdir -p ~/.codex && echo \'{auth_json}\' > ~/.codex/auth.json'

                    auth_result = container.exec_run(
                        cmd=["bash", "-c", auth_setup_cmd],
                        user="codex"
                    )

                    if auth_result.exit_code == 0:
                        logger.info("OAuth tokens injected successfully")
                        session.auth_setup_complete = True
                        return
                    else:
                        logger.warning("Failed to inject OAuth tokens",
                                     error=auth_result.output.decode('utf-8', errors='ignore'))
                elif self._oauth_tokens.get("OPENAI_API_KEY"):
                    logger.info("Using stored API key authentication", session_id=session.session_id)

                    # Create API key auth file in agent container
                    auth_json = json.dumps(self._oauth_tokens)
                    auth_setup_cmd = f'mkdir -p ~/.codex && echo \'{auth_json}\' > ~/.codex/auth.json'

                    auth_result = container.exec_run(
                        cmd=["bash", "-c", auth_setup_cmd],
                        user="codex"
                    )

                    if auth_result.exit_code == 0:
                        logger.info("API key authentication injected successfully")
                        session.auth_setup_complete = True
                        return
                    else:
                        logger.warning("Failed to inject API key authentication",
                                     error=auth_result.output.decode('utf-8', errors='ignore'))

            # Check if OAuth tokens are mounted (for non-container environments)
            oauth_check = container.exec_run(
                cmd=["test", "-f", "/app/.codex/auth.json"],
                user="codex"
            )

            if oauth_check.exit_code == 0:
                logger.info("Found OAuth auth.json file mounted in container")
                # Copy OAuth tokens to writable location for Codex CLI
                copy_result = container.exec_run(
                    cmd=["bash", "-c", "mkdir -p ~/.codex && cp /app/.codex/auth.json ~/.codex/auth.json"],
                    user="codex"
                )

                if copy_result.exit_code == 0:
                    logger.info("OAuth tokens copied from mounted directory")
                    session.auth_setup_complete = True
                    return
                else:
                    logger.warning("Failed to copy OAuth tokens from mounted directory",
                                 error=copy_result.output.decode('utf-8', errors='ignore'))

            # Fallback to API key authentication
            api_key = session.environment.get("OPENAI_API_KEY", "")
            access_token = session.environment.get("OPENAI_ACCESS_TOKEN", "")

            if access_token:
                # Use OAuth access token for authentication
                auth_content = {
                    "OPENAI_API_KEY": None,
                    "tokens": {
                        "access_token": access_token,
                        "token_type": "Bearer"
                    },
                    "last_refresh": None
                }
                auth_json = json.dumps(auth_content)
                auth_setup_cmd = f'mkdir -p ~/.codex && echo \'{auth_json}\' > ~/.codex/auth.json'

                logger.debug("Setting up OAuth access token authentication")

            elif api_key:
                # Use API key for authentication
                auth_content = {
                    "OPENAI_API_KEY": api_key,
                    "tokens": None,
                    "last_refresh": None
                }
                auth_json = json.dumps(auth_content)
                auth_setup_cmd = f'mkdir -p ~/.codex && echo \'{auth_json}\' > ~/.codex/auth.json'

                logger.debug("Setting up API key authentication")

            else:
                raise ContainerExecutionError("No authentication method available (no API key or OAuth token)")

            # Execute authentication setup
            auth_result = container.exec_run(
                cmd=["bash", "-c", auth_setup_cmd],
                user="codex",
                workdir="/app/workspace"
            )

            if auth_result.exit_code != 0:
                error_output = auth_result.output.decode('utf-8', errors='ignore')
                logger.error("Auth setup failed",
                           exit_code=auth_result.exit_code,
                           output=error_output)
                raise ContainerExecutionError(f"Auth setup failed: {error_output}")

            session.auth_setup_complete = True
            logger.debug("Codex authentication setup complete",
                        session_id=session.session_id)

        except Exception as e:
            logger.error("Failed to setup Codex authentication", error=str(e))
            raise ContainerExecutionError(f"Auth setup failed: {e}")

    async def send_message_to_codex(
        self,
        session: ContainerSession,
        message: str,
        timeout: Optional[int] = None
    ) -> str:
        """
        Send a natural language message to interactive Codex CLI session.

        This method now uses the InteractiveCodexManager for true conversational
        interaction with maintained context and workspace access.

        Args:
            session: Container session with active interactive conversation
            message: Natural language message to send
            timeout: Response timeout in seconds

        Returns:
            str: Codex CLI response

        Raises:
            ContainerExecutionError: If message sending fails
        """
        # Use configured timeout if not specified
        if timeout is None:
            timeout = self.config.server.timeouts.codex_message_timeout

        with LogContext(session.session_id):
            try:
                logger.info("Sending message to interactive Codex CLI",
                           message_preview=message[:100],
                           session_id=session.session_id,
                           timeout=timeout)

                # Use the Persistent Agent Manager for true interactive conversation
                # Check if we have a persistent agent for this session
                agent_sessions = self.persistent_agent_manager.list_active_agents()
                existing_agent = next((a for a in agent_sessions if a["session_id"] == session.session_id), None)

                if not existing_agent:
                    logger.info("Creating persistent Codex CLI agent",
                               session_id=session.session_id,
                               agent_id=session.agent_id)

                    # Prepare persistent workspace and config directories
                    persistent_workspace = await self._prepare_persistent_workspace(session)
                    persistent_config = await self._prepare_persistent_config(session)

                    agent_session = await self.persistent_agent_manager.create_persistent_agent(
                        session_id=session.session_id,
                        agent_id=session.agent_id,
                        workspace_dir=persistent_workspace,
                        client_workspace_dir=session.client_workspace_dir,
                        model=getattr(session, 'model', 'gpt-4'),
                        config_dir=persistent_config,
                        environment=session.environment,
                        bridge_script=self._get_interactive_bridge_script()
                    )

                    # Register persistent container with persistence manager for cleanup coordination
                    existing_persistent = await self.persistence_manager.get_agent_container(session.agent_id)
                    if not existing_persistent:
                        await self.persistence_manager.register_agent_container(
                            agent_id=session.agent_id,
                            container_id=agent_session.container_id or "",
                            container_name=agent_session.container_name,
                            workspace_path=persistent_workspace,
                            config_path=persistent_config,
                            model=getattr(session, 'model', 'gpt-4'),
                            reasoning=getattr(session, 'reasoning', 'medium'),
                            provider='openai',
                            approval_mode='suggest',
                            persistent_session_id=session.session_id
                        )

                    if agent_session.container_id:
                        await self.persistence_manager.update_container_status(
                            session.agent_id,
                            ContainerStatus.RUNNING
                        )

                    logger.info("Persistent Codex CLI agent created and ready",
                               session_id=session.session_id,
                               container_id=agent_session.container_id[:12])

                # Send message to the persistent agent
                response = await self.persistent_agent_manager.send_message_to_agent(
                    session_id=session.session_id,
                    message=message,
                    timeout=timeout
                )

                session.last_interaction = time.time()

                # Update persistence manager for persistent agents
                if (self.persistent_mode and session.agent_id and
                    await self.persistence_manager.get_agent_container(session.agent_id)):
                    await self.persistence_manager.update_last_active(session.agent_id)

                logger.info("Response received from persistent Codex CLI agent",
                           response_length=len(response),
                           session_id=session.session_id)

                return response

            except Exception as e:
                logger.error("Failed to send message to interactive Codex CLI",
                           session_id=session.session_id,
                           error=str(e))
                raise ContainerExecutionError(f"Interactive message sending failed: {e}")
        with LogContext(session.session_id):
            if not session.conversation_active:
                raise ContainerExecutionError("No active conversation session")

            try:
                logger.info("Sending message to Codex",
                           message_preview=message[:100],
                           session_id=session.session_id)

                # Get the container
                container = self.docker_client.containers.get(session.container_id)

                # Use Codex CLI exec mode for non-interactive execution
                # This is more reliable than interactive mode in containers
                # Escape the message properly for shell execution
                escaped_message = message.replace("'", "'\\''")

                # Setup authentication if not already done
                if not session.auth_setup_complete:
                    await self._setup_codex_auth(container, session)

                # Log the command execution to container logs
                try:
                    container.exec_run(
                        cmd=["sh", "-c", f"echo 'EXEC: codex exec --reasoning={session.reasoning} --model {session.model} \"{escaped_message[:50]}...\"' > /tmp/command_log"],
                        user="codex"
                    )
                except:
                    pass  # Don't fail if logging fails

                # Use the working exec approach we confirmed manually
                start_time = time.time()
                try:
                    # Build command with reasoning flag - try different formats if one fails
                    base_cmd = ["codex", "exec", "--skip-git-repo-check", "--dangerously-bypass-approvals-and-sandbox", "--model", session.model]

                    # Try reasoning flag format first (--reasoning=value)
                    cmd_with_reasoning = base_cmd + [f"--reasoning={session.reasoning}", escaped_message]

                    exec_result = container.exec_run(
                        cmd=cmd_with_reasoning,
                        user="codex",
                        workdir="/app/workspace",
                        environment=session.environment,
                        stdout=True,
                        stderr=True,
                        stdin=False,
                        tty=False,  # Disable TTY to avoid broken pipe issues
                        detach=False
                    )
                    execution_time = time.time() - start_time

                    # Check if reasoning flag was rejected and retry without it
                    if exec_result.exit_code != 0:
                        output = exec_result.output.decode('utf-8', errors='replace') if exec_result.output else ""
                        if "unexpected argument '--reasoning'" in output or "reasoning" in output:
                            logger.warning("Reasoning flag not supported by this Codex version, retrying without it",
                                         session_id=session.session_id)

                            # Retry without reasoning flag
                            cmd_without_reasoning = base_cmd + [escaped_message]
                            exec_result = container.exec_run(
                                cmd=cmd_without_reasoning,
                                user="codex",
                                workdir="/app/workspace",
                                environment=session.environment,
                                stdout=True,
                                stderr=True,
                                stdin=False,
                                tty=False,
                                detach=False
                            )
                            execution_time = time.time() - start_time

                    if execution_time > timeout:
                        logger.warning("Codex exec exceeded timeout",
                                     execution_time=execution_time,
                                     timeout=timeout,
                                     session_id=session.session_id)
                except Exception as docker_error:
                    logger.error("Docker exec failed",
                               error=str(docker_error),
                               session_id=session.session_id)
                    raise ContainerExecutionError(f"Docker exec failed: {docker_error}")

                # Get the output
                if exec_result.exit_code == 0:
                    response = exec_result.output.decode('utf-8', errors='ignore').strip()

                    if response:
                        logger.info("Codex exec successful",
                                   response_length=len(response),
                                   session_id=session.session_id)

                        # Log successful response to container logs
                        try:
                            container.exec_run(
                                cmd=["sh", "-c", f"echo 'RESULT: Success ({len(response)} chars)' > /tmp/command_log"],
                                user="codex"
                            )
                        except:
                            pass
                    else:
                        response = "Codex CLI executed successfully but returned no output."

                        # Log empty response to container logs
                        try:
                            container.exec_run(
                                cmd=["sh", "-c", "echo 'RESULT: No output' > /tmp/command_log"],
                                user="codex"
                            )
                        except:
                            pass

                else:
                    # Command failed, get error details
                    error_output = exec_result.output.decode('utf-8', errors='ignore').strip()
                    logger.warning("Codex exec failed",
                                 exit_code=exec_result.exit_code,
                                 error_output=error_output[:200],
                                 session_id=session.session_id)

                    # Log error to container logs
                    try:
                        container.exec_run(
                            cmd=["sh", "-c", f"echo 'ERROR: Exit code {exec_result.exit_code}' > /tmp/command_log"],
                            user="codex"
                        )
                    except:
                        pass

                    # Provide detailed error information based on exit code
                    if exec_result.exit_code == 124:  # timeout command exit code
                        response = f"""Codex CLI request timed out after {timeout} seconds.

The request was too complex or took too long to process. Consider:
1. Breaking down complex requests into smaller parts
2. Using simpler language
3. Reducing the scope of the request

Session: {session.container_id[:12]}... | Agent: {session.agent_id}
Message: "{message[:100]}..."

You can try again with a simpler request."""

                    elif exec_result.exit_code == 1:
                        response = f"""Codex CLI execution completed with an issue.

Output received: {error_output}

This might be due to:
1. Incomplete response from the AI model
2. Network connectivity interruption
3. Rate limiting from OpenAI API
4. Request complexity

Session: {session.container_id[:12]}... | Agent: {session.agent_id}
Message: "{message[:100]}..."

The partial response above may still contain useful information."""

                    elif exec_result.exit_code == 137:
                        response = f"""Codex CLI was killed (exit code 137).

This suggests:
1. Container resource limits exceeded
2. Process killed by system
3. Out of memory

Session: {session.container_id[:12]}... | Agent: {session.agent_id}
Consider using shorter, simpler requests."""

                    else:
                        response = f"""Codex CLI failed with exit code {exec_result.exit_code}.

Error output: {error_output}

Session: {session.container_id[:12]}... | Agent: {session.agent_id}"""

                session.last_interaction = time.time()

                # Update persistence manager for persistent agents
                if (self.persistent_mode and session.agent_id and
                    await self.persistence_manager.get_agent_container(session.agent_id)):
                    await self.persistence_manager.update_last_active(session.agent_id)

                logger.info("Codex response processed",
                           response_length=len(response),
                           session_id=session.session_id)

                return response

            except Exception as e:
                logger.error("Failed to send message to Codex", error=str(e))
                raise ContainerExecutionError(f"Message sending failed: {e}")

    def _is_complete_response(self, response: str) -> bool:
        """
        Heuristic to detect if Codex response is complete.

        Args:
            response: Accumulated response text

        Returns:
            bool: True if response appears complete
        """
        # Simple heuristics for response completion
        if not response:
            return False

        # Look for common Codex CLI prompt patterns
        completion_indicators_ends = [
            "codex>",  # Command prompt
            "$ ",      # Shell prompt
            "> ",      # Generic prompt
        ]

        completion_indicators_contains = [
            "Press Enter to continue",
            "Would you like me to",
            "Is there anything else",
            "anything else",
            "help with anything",
        ]

        response_lower = response.lower().strip()

        # Check for exact endings
        for indicator in completion_indicators_ends:
            if response_lower.endswith(indicator.lower().strip()):
                return True

        # Check for phrases that indicate completion
        for indicator in completion_indicators_contains:
            if indicator.lower() in response_lower:
                return True

        # If response is substantial and ends with punctuation, likely complete
        if len(response) > 50 and response.rstrip().endswith(('.', '!', '?', ':')):
            return True

        return False

    async def end_codex_conversation(self, session: ContainerSession) -> None:
        """
        End the persistent Codex CLI conversation.

        Args:
            session: Container session to end conversation for
        """
        with LogContext(session.session_id):
            if session.conversation_active and session.codex_process:
                try:
                    logger.info("Ending Codex conversation",
                               session_id=session.session_id)

                    # Send exit command to cleanly close Codex
                    try:
                        exec_result = session.codex_process
                        if exec_result:
                            # Try to gracefully close the socket
                            if hasattr(exec_result, 'output') and hasattr(exec_result.output, '_sock'):
                                sock = exec_result.output._sock
                                sock.sendall(b"exit\n")
                                sock.close()
                            elif hasattr(exec_result, '_sock'):
                                exec_result._sock.sendall(b"exit\n")
                                exec_result._sock.close()
                    except Exception:
                        pass  # Ignore cleanup errors

                    session.conversation_active = False
                    session.codex_process = None

                    logger.info("Codex conversation ended",
                               session_id=session.session_id)

                except Exception as e:
                    logger.warning("Error ending Codex conversation",
                                 error=str(e),
                                 session_id=session.session_id)

    async def _cleanup_session(self, session: ContainerSession) -> None:
        """
        Clean up session resources with proper race condition handling.

        Uses async locks to prevent concurrent cleanup of the same session.
        Handles Docker API conflicts gracefully when cleanup is already in progress.
        """
        # Ensure cleanup_lock is initialized (for sessions created before this change)
        if session.cleanup_lock is None:
            session.cleanup_lock = asyncio.Lock()

        async with session.cleanup_lock:
            # Check if cleanup is already completed
            if session.cleanup_completed:
                logger.debug("Session cleanup already completed",
                           session_id=session.session_id)
                return

            # Check if cleanup is already in progress by another task
            if session.cleanup_in_progress:
                logger.debug("Session cleanup already in progress, waiting...",
                           session_id=session.session_id)
                return

            # Mark cleanup as in progress
            session.cleanup_in_progress = True

            try:
                logger.info("Starting session cleanup", session_id=session.session_id)

                # Check if this is a persistent agent container
                is_persistent_agent = (
                    self.persistent_mode and
                    session.agent_id and
                    await self.persistence_manager.get_agent_container(session.agent_id)
                )

                if is_persistent_agent:
                    logger.info("Skipping cleanup for persistent agent container",
                               session_id=session.session_id,
                               agent_id=session.agent_id)

                    # Update last active time but don't cleanup container
                    await self.persistence_manager.update_last_active(session.agent_id)

                    # Only cleanup temporary directories if any
                    if not session.config_dir or "temp" in session.config_dir.lower():
                        await self._cleanup_directories(session)
                else:
                    # Standard cleanup for non-persistent sessions

                    # End Codex conversation first
                    if session.conversation_active:
                        try:
                            await self.end_codex_conversation(session)
                        except Exception as e:
                            logger.warning("Failed to end Codex conversation",
                                         session_id=session.session_id,
                                         error=str(e))

                    # Stop and remove container with improved error handling
                    if session.container_id:
                        await self._cleanup_container(session)

                    # Clean up directories
                    await self._cleanup_directories(session)

                # Mark cleanup as completed
                session.cleanup_completed = True
                session.status = "cleaned_up"

                logger.info("Session cleanup completed successfully",
                           session_id=session.session_id)

            except Exception as e:
                session.cleanup_error = str(e)
                logger.error("Session cleanup failed",
                           session_id=session.session_id,
                           error=str(e))
                raise
            finally:
                session.cleanup_in_progress = False

    async def _cleanup_container(self, session: ContainerSession) -> None:
        """Clean up Docker container with proper conflict handling."""
        container_id = session.container_id
        if not container_id:
            return

        try:
            # First, check if container exists
            try:
                container = self.docker_client.containers.get(container_id)
            except NotFound:
                logger.debug("Container already removed",
                           container_id=container_id[:12])
                return

            # Stop container if running
            if container.status == "running":
                try:
                    container.stop(timeout=10)
                    logger.debug("Container stopped",
                               container_id=container_id[:12])
                except Exception as e:
                    logger.debug("Container stop failed (may already be stopped)",
                               container_id=container_id[:12],
                               error=str(e))

            # Remove container
            try:
                container.remove(force=True)
                logger.debug("Container removed successfully",
                           container_id=container_id[:12])
            except APIError as e:
                if e.status_code == 409:
                    # Container removal already in progress - this is expected
                    logger.debug("Container removal already in progress",
                               container_id=container_id[:12])
                else:
                    logger.warning("Container removal API error",
                                 container_id=container_id[:12],
                                 status_code=e.status_code,
                                 error=str(e))
            except NotFound:
                # Container was already removed between our check and removal attempt
                logger.debug("Container was already removed during cleanup",
                           container_id=container_id[:12])

        except Exception as e:
            logger.warning("Unexpected error during container cleanup",
                         container_id=container_id[:12],
                         error=str(e))

    async def _cleanup_directories(self, session: ContainerSession) -> None:
        """Clean up session directories."""
        for dir_path in [session.config_dir, session.workspace_dir]:
            if dir_path and Path(dir_path).exists():
                try:
                    import shutil
                    shutil.rmtree(dir_path)
                    logger.debug("Directory removed", path=dir_path)
                except Exception as e:
                    logger.warning("Failed to remove directory",
                                 path=dir_path,
                                 error=str(e))

    async def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a session."""
        session = self.active_sessions.get(session_id)
        if not session:
            return None

        info = {
            "session_id": session.session_id,
            "agent_id": session.agent_id,
            "status": session.status,
            "created_at": session.created_at,
            "container_id": session.container_id,
            "container_name": session.container_name
        }

        # Get container status if available
        if session.container_id:
            try:
                container = self.docker_client.containers.get(session.container_id)
                info["container_status"] = container.status
                info["container_stats"] = container.stats(stream=False)
            except Exception:
                info["container_status"] = "unknown"

        return info

    async def list_active_sessions(self) -> List[Dict[str, Any]]:
        """List all active sessions."""
        sessions = []
        for session_id in list(self.active_sessions.keys()):
            session_info = await self.get_session_info(session_id)
            if session_info:
                sessions.append(session_info)
        return sessions

    async def cleanup_all_sessions(self) -> None:
        """Clean up all active sessions."""
        logger.info("Cleaning up all sessions", count=len(self.active_sessions))

        cleanup_tasks = []
        for session in list(self.active_sessions.values()):
            cleanup_tasks.append(self._cleanup_session(session))

        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)

        self.active_sessions.clear()
        logger.info("All sessions cleaned up")

    # === Persistent Agent Management Methods ===

    async def list_active_agents(self) -> List[Dict[str, Any]]:
        """
        List all active agent containers.

        Returns:
            List[Dict[str, Any]]: List of active agent information
        """
        if not self.persistent_mode:
            return []

        active_agents = await self.persistence_manager.list_active_agents()
        result = []

        for agent_info in active_agents:
            try:
                # Check actual container status
                container = self.docker_client.containers.get(agent_info.container_id)
                container_status = container.status

                # Get resource usage if available
                try:
                    stats = container.stats(stream=False)
                    cpu_percent = self._calculate_cpu_percent(stats)
                    memory_usage = stats['memory_stats'].get('usage', 0)
                    memory_limit = stats['memory_stats'].get('limit', 0)
                except Exception:
                    cpu_percent = 0
                    memory_usage = 0
                    memory_limit = 0

                result.append({
                    "agent_id": agent_info.agent_id,
                    "container_id": agent_info.container_id,
                    "container_name": agent_info.container_name,
                    "status": container_status,
                    "created_at": agent_info.created_at,
                    "last_active": agent_info.last_active,
                    "model": agent_info.model,
                    "cpu_percent": cpu_percent,
                    "memory_usage_mb": memory_usage // (1024 * 1024),
                    "memory_limit_mb": memory_limit // (1024 * 1024),
                    "workspace_path": agent_info.workspace_path
                })

            except NotFound:
                # Container no longer exists, mark for removal
                logger.warning("Container no longer exists, removing from persistence",
                             agent_id=agent_info.agent_id,
                             container_id=agent_info.container_id[:12])
                await self.persistence_manager.remove_agent_container(agent_info.agent_id)

            except Exception as e:
                logger.error("Error getting agent container info",
                           agent_id=agent_info.agent_id,
                           error=str(e))

        return result

    async def stop_agent_container(self, agent_id: str) -> Dict[str, Any]:
        """
        Stop a specific agent container.

        Args:
            agent_id: Agent identifier

        Returns:
            Dict[str, Any]: Operation result
        """
        if not self.persistent_mode:
            return {"success": False, "message": "Persistent mode not enabled"}

        agent_info = await self.persistence_manager.get_agent_container(agent_id)
        if not agent_info:
            return {"success": False, "message": f"Agent {agent_id} not found"}

        try:
            container = self.docker_client.containers.get(agent_info.container_id)

            if container.status == "running":
                container.stop(timeout=10)
                logger.info("Agent container stopped",
                           agent_id=agent_id,
                           container_id=agent_info.container_id[:12])

            # Update persistence
            await self.persistence_manager.update_container_status(
                agent_id,
                ContainerStatus.STOPPED
            )

            return {
                "success": True,
                "message": f"Agent {agent_id} container stopped",
                "container_id": agent_info.container_id[:12]
            }

        except NotFound:
            await self.persistence_manager.remove_agent_container(agent_id)
            return {"success": False, "message": f"Container for agent {agent_id} not found"}

        except Exception as e:
            logger.error("Failed to stop agent container",
                        agent_id=agent_id,
                        error=str(e))
            return {"success": False, "message": f"Failed to stop container: {e}"}

    async def restart_agent_container(self, agent_id: str) -> Dict[str, Any]:
        """
        Restart a specific agent container.

        Args:
            agent_id: Agent identifier

        Returns:
            Dict[str, Any]: Operation result
        """
        if not self.persistent_mode:
            return {"success": False, "message": "Persistent mode not enabled"}

        agent_info = await self.persistence_manager.get_agent_container(agent_id)
        if not agent_info:
            return {"success": False, "message": f"Agent {agent_id} not found"}

        try:
            container = self.docker_client.containers.get(agent_info.container_id)

            # Stop if running
            if container.status == "running":
                container.stop(timeout=10)

            # Start the container
            container.start()

            # Wait for it to be running
            max_wait = 30
            wait_time = 0
            while wait_time < max_wait:
                container.reload()
                if container.status == "running":
                    break
                await asyncio.sleep(1)
                wait_time += 1

            if container.status == "running":
                await self.persistence_manager.update_container_status(
                    agent_id,
                    ContainerStatus.RUNNING
                )

                logger.info("Agent container restarted",
                           agent_id=agent_id,
                           container_id=agent_info.container_id[:12])

                return {
                    "success": True,
                    "message": f"Agent {agent_id} container restarted",
                    "container_id": agent_info.container_id[:12]
                }
            else:
                return {"success": False, "message": f"Container failed to start within {max_wait} seconds"}

        except NotFound:
            await self.persistence_manager.remove_agent_container(agent_id)
            return {"success": False, "message": f"Container for agent {agent_id} not found"}

        except Exception as e:
            logger.error("Failed to restart agent container",
                        agent_id=agent_id,
                        error=str(e))
            return {"success": False, "message": f"Failed to restart container: {e}"}

    async def remove_agent_container(self, agent_id: str) -> Dict[str, Any]:
        """
        Permanently remove an agent container and all its data.

        Args:
            agent_id: Agent identifier

        Returns:
            Dict[str, Any]: Operation result
        """
        if not self.persistent_mode:
            return {"success": False, "message": "Persistent mode not enabled"}

        agent_info = await self.persistence_manager.get_agent_container(agent_id)
        if not agent_info:
            return {"success": False, "message": f"Agent {agent_id} not found"}

        try:
            # Stop and remove container
            try:
                container = self.docker_client.containers.get(agent_info.container_id)
                if container.status == "running":
                    container.stop(timeout=10)
                container.remove(force=True)
                logger.info("Agent container removed",
                           agent_id=agent_id,
                           container_id=agent_info.container_id[:12])
            except NotFound:
                logger.debug("Container already removed",
                           container_id=agent_info.container_id[:12])

            # Remove persistent data
            agent_data_path = Path(self.persistence_manager.data_path) / "agents" / agent_id
            if agent_data_path.exists():
                import shutil
                shutil.rmtree(agent_data_path, ignore_errors=True)
                logger.debug("Agent data directory removed",
                           path=str(agent_data_path))

            # Remove from persistence
            await self.persistence_manager.remove_agent_container(agent_id)

            return {
                "success": True,
                "message": f"Agent {agent_id} completely removed",
                "container_id": agent_info.container_id[:12]
            }

        except Exception as e:
            logger.error("Failed to remove agent container",
                        agent_id=agent_id,
                        error=str(e))
            return {"success": False, "message": f"Failed to remove container: {e}"}

    async def get_agent_status(self, agent_id: str) -> Dict[str, Any]:
        """
        Get detailed status for a specific agent.

        Args:
            agent_id: Agent identifier

        Returns:
            Dict[str, Any]: Agent status information
        """
        if not self.persistent_mode:
            return {"success": False, "message": "Persistent mode not enabled"}

        agent_info = await self.persistence_manager.get_agent_container(agent_id)
        if not agent_info:
            return {"success": False, "message": f"Agent {agent_id} not found"}

        try:
            container = self.docker_client.containers.get(agent_info.container_id)

            # Get container logs (last 50 lines)
            logs = container.logs(tail=50).decode('utf-8', errors='ignore')

            # Get resource stats
            try:
                stats = container.stats(stream=False)
                cpu_percent = self._calculate_cpu_percent(stats)
                memory_usage = stats['memory_stats'].get('usage', 0)
                memory_limit = stats['memory_stats'].get('limit', 0)
            except Exception:
                cpu_percent = 0
                memory_usage = 0
                memory_limit = 0

            return {
                "success": True,
                "agent_id": agent_id,
                "container_id": agent_info.container_id,
                "container_name": agent_info.container_name,
                "status": container.status,
                "created_at": agent_info.created_at,
                "last_active": agent_info.last_active,
                "model": agent_info.model,
                "provider": agent_info.provider,
                "cpu_percent": cpu_percent,
                "memory_usage_mb": memory_usage // (1024 * 1024),
                "memory_limit_mb": memory_limit // (1024 * 1024),
                "workspace_path": agent_info.workspace_path,
                "config_path": agent_info.config_path,
                "recent_logs": logs.split('\n')[-10:]  # Last 10 lines
            }

        except NotFound:
            await self.persistence_manager.remove_agent_container(agent_id)
            return {"success": False, "message": f"Container for agent {agent_id} not found"}

        except Exception as e:
            logger.error("Failed to get agent status",
                        agent_id=agent_id,
                        error=str(e))
            return {"success": False, "message": f"Failed to get status: {e}"}

    async def cleanup_inactive_agents(self, inactive_hours: int = 24) -> Dict[str, Any]:
        """
        Remove agent containers that have been inactive for specified time.

        Args:
            inactive_hours: Hours of inactivity before removal

        Returns:
            Dict[str, Any]: Cleanup results
        """
        if not self.persistent_mode:
            return {"success": False, "message": "Persistent mode not enabled"}

        inactive_threshold = inactive_hours * 3600  # Convert to seconds
        inactive_agents = await self.persistence_manager.list_inactive_agents(inactive_threshold)

        removed_agents = []
        failed_removals = []

        for agent_info in inactive_agents:
            try:
                result = await self.remove_agent_container(agent_info.agent_id)
                if result["success"]:
                    removed_agents.append(agent_info.agent_id)
                else:
                    failed_removals.append({
                        "agent_id": agent_info.agent_id,
                        "error": result["message"]
                    })
            except Exception as e:
                failed_removals.append({
                    "agent_id": agent_info.agent_id,
                    "error": str(e)
                })

        return {
            "success": True,
            "removed_agents": removed_agents,
            "failed_removals": failed_removals,
            "total_removed": len(removed_agents),
            "total_failed": len(failed_removals)
        }

    def _get_oauth_directory(self) -> Optional[str]:
        """
        Get the OAuth token directory path if it exists.

        Returns:
            Path to OAuth directory or None if not available
        """
        try:
            # When running in container mode, read OAuth tokens from main container
            # and inject them into agent containers rather than mounting
            container_oauth_path = Path("/app/.codex")
            if container_oauth_path.exists() and (container_oauth_path / "auth.json").exists():
                logger.info("Found OAuth directory in main container mount", path=str(container_oauth_path))

                # Store OAuth tokens for injection into agent containers
                try:
                    with open(container_oauth_path / "auth.json") as f:
                        auth_data = json.load(f)

                    if auth_data.get("tokens") and auth_data["tokens"].get("access_token"):
                        logger.info("Verified OAuth tokens - will inject into agent containers")
                        # Store the OAuth data for injection, don't mount the directory
                        self._oauth_tokens = auth_data
                        return None  # Don't mount, use injection approach
                    elif auth_data.get("OPENAI_API_KEY"):
                        logger.info("Found API key authentication - will inject into agent containers")
                        self._oauth_tokens = auth_data
                        return None  # Don't mount, use injection approach

                except json.JSONDecodeError:
                    logger.warning("Mounted auth.json exists but is not valid JSON")

            # Check the actual path where your OAuth tokens are stored (host system)
            codex_home = Path.home() / ".codex"
            if codex_home.exists() and (codex_home / "auth.json").exists():
                logger.info("Found OAuth directory with auth.json", path=str(codex_home))

                # Verify it contains OAuth tokens
                try:
                    with open(codex_home / "auth.json") as f:
                        auth_data = json.load(f)

                    if auth_data.get("tokens") and auth_data["tokens"].get("access_token"):
                        logger.info("Verified OAuth tokens in auth.json")
                        return str(codex_home)
                    elif auth_data.get("OPENAI_API_KEY"):
                        logger.info("Found API key authentication in auth.json")
                        return str(codex_home)
                    else:
                        logger.warning("auth.json exists but format is unclear")
                        return str(codex_home)  # Mount anyway, let container handle it

                except json.JSONDecodeError:
                    logger.warning("auth.json exists but is not valid JSON")
                    return None

                return str(codex_home)

            # Also check for explicitly set OAuth token storage path
            oauth_path = os.getenv("CODEX_OAUTH_PATH")
            if oauth_path:
                oauth_dir = Path(oauth_path).parent
                if oauth_dir.exists():
                    logger.debug("Found custom OAuth directory", path=str(oauth_dir))
                    return str(oauth_dir)

            logger.debug("No OAuth directory found")
            return None

        except Exception as e:
            logger.warning("Error checking OAuth directory", error=str(e))
            return None

    def _calculate_cpu_percent(self, stats: Dict[str, Any]) -> float:
        """Calculate CPU usage percentage from Docker stats."""
        try:
            cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                       stats['precpu_stats']['cpu_usage']['total_usage']
            system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                          stats['precpu_stats']['system_cpu_usage']

            if system_delta > 0:
                cpu_percent = (cpu_delta / system_delta) * \
                             len(stats['cpu_stats']['cpu_usage']['percpu_usage']) * 100
                return round(cpu_percent, 2)
        except (KeyError, ZeroDivisionError):
            pass
        return 0.0

    def __del__(self):
        """Ensure cleanup on destruction."""
        try:
            # Try to clean up any remaining sessions
            if hasattr(self, 'active_sessions') and self.active_sessions:
                logger.warning("Container manager destroyed with active sessions",
                             count=len(self.active_sessions))
        except Exception:
            pass
