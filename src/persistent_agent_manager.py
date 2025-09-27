"""
Persistent Agent Manager for Interactive Codex CLI Sessions.

This manager handles truly persistent Codex CLI agents that run continuously
in containers and communicate via message pipes, with full conversation
visibility in Docker logs.
"""

import asyncio
import time
import os
import textwrap
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from pathlib import Path
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PersistentAgentSession:
    """Represents a persistent interactive Codex CLI agent session."""
    session_id: str
    agent_id: str
    container_id: Optional[str] = None
    container_name: str = ""
    created_at: float = 0.0
    status: str = "initializing"

    # Communication channels
    message_pipe_in: Optional[str] = None
    message_pipe_out: Optional[str] = None

    # Agent state
    agent_ready: bool = False
    last_message_time: float = 0.0
    conversation_count: int = 0

    # Workspace integration
    client_workspace_dir: Optional[str] = None
    config_dir: Optional[str] = None
    environment: Dict[str, str] = field(default_factory=dict)


class PersistentAgentManager:
    """
    Manager for persistent interactive Codex CLI agents.

    This creates containers where Codex CLI runs continuously and interactively,
    with message-based communication and full conversation logging.
    """

    def __init__(self, docker_client, config):
        """Initialize the persistent agent manager."""
        self.docker_client = docker_client
        self.config = config
        self.active_agents: Dict[str, PersistentAgentSession] = {}

    async def create_persistent_agent(
        self,
        session_id: str,
        agent_id: str,
        workspace_dir: str,
        client_workspace_dir: Optional[str] = None,
        model: str = "gpt-4",
        config_dir: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
        bridge_script: Optional[str] = None
    ) -> PersistentAgentSession:
        """
        Create a persistent interactive Codex CLI agent.

        This starts a container with a continuously running Codex CLI agent
        that can receive and respond to messages via named pipes.
        """
        logger.info("Creating persistent interactive Codex CLI agent",
                   session_id=session_id,
                   agent_id=agent_id,
                   model=model,
                   has_client_workspace=client_workspace_dir is not None)

        session = PersistentAgentSession(
            session_id=session_id,
            agent_id=agent_id,
            container_name=f"codex-agent-{session_id}",
            created_at=time.time(),
            client_workspace_dir=client_workspace_dir,
            config_dir=config_dir,
            environment=environment or {}
        )

        try:
            # Create and start the container with the interactive agent
            await self._create_agent_container(
                session=session,
                workspace_dir=workspace_dir,
                model=model,
                container_environment=environment or {},
                bridge_script=bridge_script
            )

            # Wait for the agent to be ready
            await self._wait_for_agent_ready(session)

            # Register the session
            self.active_agents[session_id] = session
            session.status = "ready"

            logger.info("Persistent interactive Codex CLI agent created successfully",
                       session_id=session_id,
                       container_id=session.container_id[:12])

            return session

        except Exception as e:
            logger.error("Failed to create persistent agent",
                        session_id=session_id,
                        error=str(e))
            await self._cleanup_failed_session(session)
            raise

    async def _create_agent_container(
        self,
        session: PersistentAgentSession,
        workspace_dir: str,
        model: str,
        container_environment: Dict[str, str],
        bridge_script: Optional[str]
    ) -> None:
        """Create the Docker container with persistent interactive Codex CLI agent."""

        # Determine workspace to mount - prioritize client workspace for real directory access
        workspace_to_mount = session.client_workspace_dir or workspace_dir
        abs_workspace = os.path.abspath(workspace_to_mount)

        # Container environment for interactive agent
        environment = dict(container_environment)
        environment.update({
            "CODEX_MODEL": model,
            "SESSION_ID": session.session_id,
            "AGENT_ID": session.agent_id,
            "WORKSPACE_DIR": "/app/workspace"
        })

        # Ensure basic terminal settings for interactive codex CLI
        environment.setdefault("TERM", "xterm-256color")
        environment.setdefault("HOME", "/app")
        environment.setdefault("PYTHONUNBUFFERED", "1")

        # Volume mounts - mount the REAL workspace directory
        volumes = {
            abs_workspace: {"bind": "/app/workspace", "mode": "rw"}
        }

        if session.config_dir:
            abs_config_dir = os.path.abspath(session.config_dir)
            volumes[abs_config_dir] = {"bind": "/app/config", "mode": "ro"}
            logger.debug(
                "Mounting session config directory",
                session_id=session.session_id,
                config_dir=abs_config_dir
            )

        logger.info("Creating container for persistent interactive agent",
                   session_id=session.session_id,
                   workspace_source=abs_workspace,
                   model=model,
                   real_directory_access=session.client_workspace_dir is not None)

        bridge_script = bridge_script or "print('Interactive Codex bridge unavailable.')"

        bridge_script = bridge_script.replace("__CODEX_BRIDGE__", "__CODEX_CUSTOM_BRIDGE__")

        command_script = textwrap.dedent(f"""
            echo "=== Starting Codex CLI Agent Container ==="
            echo "Working directory: $(pwd)"
            echo "User: $(whoami)"
            mkdir -p /tmp
            cat <<'__CODEX_BRIDGE__' > /tmp/interactive_codex_agent.py
{bridge_script}
__CODEX_BRIDGE__
            chmod 755 /tmp/interactive_codex_agent.py
            cd /app/workspace
            echo "Changed to workspace: $(pwd)"
            echo "Workspace contents:"
            ls -la . || echo "Workspace empty or not accessible"
            echo "Starting Codex CLI..."
            exec python3 /tmp/interactive_codex_agent.py
        """)

        try:
            # Create container that runs the interactive Codex CLI agent script
            container = self.docker_client.containers.create(
                image="codex-mcp-base",
                entrypoint=[],  # Completely clear the entrypoint
                command=["bash", "-lc", command_script],
                name=session.container_name,
                environment=environment,
                volumes=volumes,
                working_dir="/app",
                user="codex",
                detach=True,
                tty=True,  # Enable TTY for interactive bridge
                stdin_open=True,  # Keep STDIN open
                # Resource limits for interactive agent
                mem_limit="4g",  # More memory for persistent agent
                cpu_period=100000,
                cpu_quota=400000,  # 4 CPU cores for better performance
                # Networking
                network_mode="bridge"
            )

            session.container_id = container.id

            # Start the container
            container.start()

            logger.info("Interactive Codex CLI agent container started",
                       session_id=session.session_id,
                       container_id=container.id[:12],
                       real_workspace_mounted=abs_workspace)

            # Copy authentication material into writable Codex home if mounted
            if session.config_dir:
                auth_copy_result = container.exec_run(
                    cmd=[
                        "bash",
                        "-c",
                        "mkdir -p ~/.codex && cp /app/config/auth.json ~/.codex/auth.json && chmod 600 ~/.codex/auth.json"
                    ],
                    user="codex"
                )

                if auth_copy_result.exit_code != 0:
                    logger.warning(
                        "Failed to copy auth.json into container",
                        session_id=session.session_id,
                        error=auth_copy_result.output.decode("utf-8", errors="ignore")
                    )

            # Set up message communication file paths (inside container)
            session.message_pipe_in = "/tmp/codex_messages/incoming.msg"
            session.message_pipe_out = "/tmp/codex_messages/response.msg"

        except Exception as e:
            logger.error("Failed to create interactive agent container",
                        session_id=session.session_id,
                        error=str(e))
            raise

    async def _wait_for_agent_ready(self, session: PersistentAgentSession, timeout: int = 60) -> None:
        """Wait for the persistent agent to be ready for communication."""
        logger.info("Waiting for persistent agent to be ready",
                   session_id=session.session_id,
                   timeout=timeout)

        start_time = time.time()
        container = self.docker_client.containers.get(session.container_id)

        while time.time() - start_time < timeout:
            try:
                # Check if container is still running
                container.reload()
                if container.status != "running":
                    raise Exception(f"Container stopped unexpectedly: {container.status}")

                # Check bridge status file introduced in interactive bridge script
                status_check = container.exec_run(
                    cmd=["bash", "-c", "cat /tmp/codex_messages/status 2>/dev/null"],
                    user="codex"
                )

                if status_check.exit_code == 0:
                    status_text = status_check.output.decode("utf-8", errors="ignore").strip()
                    if status_text in {"agent_ready", "waiting_for_message", "processing"}:
                        logger.info(
                            "Persistent agent bridge reported ready",
                            session_id=session.session_id,
                            status=status_text
                        )
                        session.agent_ready = True
                        return

                # Backwards compatibility: check legacy pipe path if bridge status not found
                exec_result = container.exec_run(
                    cmd=["test", "-p", "/tmp/codex_pipes/messages_in"],
                    user="codex"
                )

                if exec_result.exit_code == 0:
                    logger.info("Legacy persistent agent pipes detected",
                               session_id=session.session_id)
                    session.agent_ready = True
                    return

            except Exception as e:
                logger.debug("Agent readiness check failed, retrying",
                           session_id=session.session_id,
                           error=str(e))

            await asyncio.sleep(2)

        raise Exception(f"Persistent agent did not become ready within {timeout} seconds")

    async def send_message_to_agent(
        self,
        session_id: str,
        message: str,
        timeout: Optional[int] = None
    ) -> str:
        """
        Send a message to the persistent interactive Codex CLI agent.

        This writes the message to the agent's message file, waits for processing,
        and returns the response. The full conversation is visible in Docker logs.
        """
        session = self.active_agents.get(session_id)
        if not session:
            raise ValueError(f"No active agent session: {session_id}")

        if not session.agent_ready:
            raise ValueError(f"Agent not ready: {session_id}")

        # Use configured timeout if not specified
        if timeout is None:
            timeout = self.config.server.timeouts.codex_message_timeout

        logger.info("Sending message to persistent interactive agent",
                   session_id=session_id,
                   message_preview=message[:100],
                   timeout=timeout)

        try:
            container = self.docker_client.containers.get(session.container_id)

            # Clean previous response file
            cleanup_cmd = f"rm -f {session.message_pipe_out}"
            container.exec_run(cmd=["bash", "-c", cleanup_cmd], user="codex")

            # Write message to the agent's input file
            # Escape message properly for shell
            escaped_message = message.replace('"', '\\"').replace('`', '\\`').replace('$', '\\$')
            send_command = f'echo "{escaped_message}" > {session.message_pipe_in}'

            exec_result = container.exec_run(
                cmd=["bash", "-c", send_command],
                user="codex"
            )

            if exec_result.exit_code != 0:
                error_msg = exec_result.output.decode('utf-8', errors='ignore') if exec_result.output else "Unknown error"
                raise Exception(f"Failed to send message to agent: {error_msg}")

            logger.debug("Message written to agent input file",
                        session_id=session_id,
                        input_file=session.message_pipe_in)

            # Wait for the agent to process the message and generate response
            response = await self._wait_for_agent_response(session, timeout)

            # Update session stats
            session.last_message_time = time.time()
            session.conversation_count += 1

            logger.info("Response received from persistent interactive agent",
                       session_id=session_id,
                       response_length=len(response),
                       conversation_count=session.conversation_count)

            return response

        except Exception as e:
            logger.error("Failed to communicate with persistent interactive agent",
                        session_id=session_id,
                        error=str(e))
            raise

    async def _wait_for_agent_response(
        self,
        session: PersistentAgentSession,
        timeout: int
    ) -> str:
        """Wait for the interactive agent to process the message and generate a response."""
        container = self.docker_client.containers.get(session.container_id)
        start_time = time.time()

        logger.debug("Waiting for agent response",
                    session_id=session.session_id,
                    timeout=timeout,
                    response_file=session.message_pipe_out)

        # Wait for the response file to be created and populated
        while time.time() - start_time < timeout:
            try:
                # Check if response file exists and has content
                check_response_cmd = f"test -f {session.message_pipe_out} && test -s {session.message_pipe_out}"
                check_result = container.exec_run(
                    cmd=["bash", "-c", check_response_cmd],
                    user="codex"
                )

                if check_result.exit_code == 0:
                    # Response file exists and has content, read it
                    read_cmd = f"cat {session.message_pipe_out}"
                    read_result = container.exec_run(
                        cmd=["bash", "-c", read_cmd],
                        user="codex"
                    )

                    if read_result.exit_code == 0 and read_result.output:
                        response = read_result.output.decode('utf-8', errors='ignore').strip()

                        if response and response != "PROCESSING":
                            logger.debug(
                                "Agent response captured",
                                session_id=session.session_id,
                                response_preview=response[:200],
                                response_length=len(response),
                            )
                            logger.debug("Agent response received",
                                       session_id=session.session_id,
                                       response_length=len(response))
                            return response

            except Exception as e:
                logger.debug("Error checking for agent response",
                           session_id=session.session_id,
                           error=str(e))

            await asyncio.sleep(2)  # Check every 2 seconds

        # Timeout reached, try to get any partial response or status
        try:
            status_check = container.exec_run(
                cmd=["bash", "-c", f"cat /tmp/codex_messages/status 2>/dev/null || echo 'unknown'"],
                user="codex"
            )
            status = status_check.output.decode('utf-8', errors='ignore').strip() if status_check.output else "unknown"

            logger.warning("Agent response timeout",
                         session_id=session.session_id,
                         timeout=timeout,
                         agent_status=status)

        except Exception:
            pass

        return f"Agent did not respond within {timeout} seconds. The agent may be processing a complex request or experiencing issues."

    def _is_response_complete(self, response: str) -> bool:
        """Check if the agent response appears complete."""
        # Simple heuristic - look for typical Codex completion patterns
        completion_indicators = [
            "anything else",
            "help you with",
            "let me know",
            "is there",
            "feel free"
        ]

        response_lower = response.lower()
        return any(indicator in response_lower for indicator in completion_indicators)

    async def get_agent_logs(self, session_id: str, tail_lines: int = 50) -> List[str]:
        """Get recent logs from the persistent agent for debugging."""
        session = self.active_agents.get(session_id)
        if not session:
            raise ValueError(f"No active agent session: {session_id}")

        try:
            container = self.docker_client.containers.get(session.container_id)
            logs = container.logs(tail=tail_lines, timestamps=True).decode('utf-8')
            return logs.split('\n')
        except Exception as e:
            logger.error("Failed to get agent logs",
                        session_id=session_id,
                        error=str(e))
            return [f"Error getting logs: {str(e)}"]

    async def stop_persistent_agent(self, session_id: str) -> bool:
        """Stop and cleanup a persistent agent session."""
        session = self.active_agents.get(session_id)
        if not session:
            return False

        logger.info("Stopping persistent agent",
                   session_id=session_id,
                   conversation_count=session.conversation_count)

        try:
            if session.container_id:
                container = self.docker_client.containers.get(session.container_id)
                container.stop(timeout=10)
                container.remove()

            # Remove from active sessions
            del self.active_agents[session_id]

            logger.info("Persistent agent stopped and cleaned up",
                       session_id=session_id)
            return True

        except Exception as e:
            logger.error("Error stopping persistent agent",
                        session_id=session_id,
                        error=str(e))
            return False

    async def _cleanup_failed_session(self, session: PersistentAgentSession) -> None:
        """Clean up a failed session attempt."""
        try:
            if session.container_id:
                container = self.docker_client.containers.get(session.container_id)
                container.stop(timeout=5)
                container.remove()
        except Exception as e:
            logger.debug("Error during failed session cleanup",
                        session_id=session.session_id,
                        error=str(e))

    def list_active_agents(self) -> List[Dict[str, Any]]:
        """List all active persistent agents."""
        return [
            {
                "session_id": session.session_id,
                "agent_id": session.agent_id,
                "status": session.status,
                "created_at": session.created_at,
                "conversation_count": session.conversation_count,
                "last_message_time": session.last_message_time,
                "container_id": session.container_id[:12] if session.container_id else None,
                "agent_ready": session.agent_ready
            }
            for session in self.active_agents.values()
        ]
