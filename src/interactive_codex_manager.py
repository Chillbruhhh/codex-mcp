"""
Interactive Codex CLI Manager for enhanced agent collaboration.

This module provides the core functionality for running Codex CLI in fully
interactive mode with persistent conversations and workspace integration.
"""

import asyncio
import time
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class InteractiveSession:
    """Enhanced session for interactive Codex CLI collaboration."""
    session_id: str
    agent_id: str

    # Interactive process handles
    codex_process: Optional[Any] = None
    codex_stdin: Optional[Any] = None
    codex_stdout: Optional[Any] = None
    codex_stderr: Optional[Any] = None

    # Conversation state
    conversation_active: bool = False
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)
    last_interaction: float = field(default_factory=time.time)

    # Workspace integration
    client_workspace_dir: Optional[str] = None
    workspace_context_initialized: bool = False


class InteractiveCodexManager:
    """
    Manager for interactive Codex CLI sessions.

    Handles the creation and management of persistent interactive Codex CLI
    processes that can maintain conversation state and collaborate directly
    with MCP clients on their workspace files.
    """

    def __init__(self):
        """Initialize the interactive manager."""
        self.active_sessions: Dict[str, InteractiveSession] = {}

    async def start_interactive_session(
        self,
        container,
        session_id: str,
        agent_id: str,
        workspace_dir: str = "/app/workspace",
        client_workspace_dir: Optional[str] = None
    ) -> InteractiveSession:
        """
        Start a fully interactive Codex CLI session.

        Args:
            container: Docker container instance
            session_id: Unique session identifier
            agent_id: Agent identifier
            workspace_dir: Container workspace directory path
            client_workspace_dir: Client's actual workspace directory path

        Returns:
            InteractiveSession: Active interactive session

        Raises:
            Exception: If session startup fails
        """
        logger.info("Starting interactive Codex CLI session",
                   session_id=session_id,
                   agent_id=agent_id,
                   workspace_dir=workspace_dir,
                   has_client_workspace=client_workspace_dir is not None)

        session = InteractiveSession(
            session_id=session_id,
            agent_id=agent_id,
            client_workspace_dir=client_workspace_dir
        )

        try:
            # Start Codex CLI in interactive mode
            exec_result = container.exec_run(
                cmd=[
                    "bash", "-c",
                    f"cd {workspace_dir} && codex --interactive --no-exit-on-error"
                ],
                stdin=True,
                stdout=True,
                stderr=True,
                tty=False,  # Disable TTY for programmatic control
                user="codex",
                workdir=workspace_dir,
                detach=True,  # Keep running persistently
                stream=True   # Enable streaming I/O
            )

            # Store process and stream handles
            session.codex_process = exec_result

            # Set up stream access
            if hasattr(exec_result, 'output'):
                # Docker SDK provides socket-like interface
                socket = exec_result.output
                session.codex_stdin = socket
                session.codex_stdout = socket
                session.codex_stderr = socket
            else:
                # Fallback to process streams
                session.codex_stdin = exec_result
                session.codex_stdout = exec_result
                session.codex_stderr = exec_result

            session.conversation_active = True

            # Initialize conversation context
            await self._initialize_workspace_context(session, workspace_dir)

            # Register session
            self.active_sessions[session_id] = session

            logger.info("Interactive Codex CLI session started successfully",
                       session_id=session_id,
                       agent_id=agent_id)

            return session

        except Exception as e:
            logger.error("Failed to start interactive Codex CLI session",
                        session_id=session_id,
                        error=str(e))
            raise

    async def _initialize_workspace_context(
        self,
        session: InteractiveSession,
        workspace_dir: str
    ) -> None:
        """Initialize the Codex CLI session with workspace context."""
        try:
            context_messages = [
                f"🤝 Interactive collaboration session started",
                f"📁 Working directory: {workspace_dir}",
                f"🤖 Collaborating with MCP agent: {session.agent_id}",
                f"⏰ Session started: {time.strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                "I'm ready to help with your development tasks!",
                "I have full access to your workspace and can:",
                "• Read and analyze existing code",
                "• Create and modify files",
                "• Run commands and tests",
                "• Maintain conversation context across interactions",
                "",
                "What would you like to work on together?"
            ]

            context_message = "\n".join(context_messages)

            # Store in conversation history as initial context
            session.conversation_history.append({
                "type": "system_initialization",
                "message": context_message,
                "timestamp": time.time()
            })

            session.workspace_context_initialized = True

            logger.debug("Workspace context initialized",
                        session_id=session.session_id,
                        workspace_dir=workspace_dir)

        except Exception as e:
            logger.warning("Failed to initialize workspace context",
                          session_id=session.session_id,
                          error=str(e))

    async def send_interactive_message(
        self,
        session_id: str,
        message: str,
        timeout: int = 300
    ) -> str:
        """
        Send message to interactive Codex CLI session.

        Args:
            session_id: Session identifier
            message: Message to send
            timeout: Response timeout in seconds

        Returns:
            str: Codex CLI response

        Raises:
            ValueError: If session not found
            Exception: If communication fails
        """
        session = self.active_sessions.get(session_id)
        if not session:
            raise ValueError(f"Interactive session {session_id} not found")

        if not session.conversation_active:
            raise ValueError(f"Session {session_id} is not active")

        logger.info("Sending interactive message",
                   session_id=session_id,
                   message_preview=message[:100])

        try:
            # Record message in history
            session.conversation_history.append({
                "type": "user_message",
                "message": message,
                "timestamp": time.time()
            })

            # Send message to Codex CLI
            start_time = time.time()

            formatted_message = f"{message}\n"

            # Send via stdin
            if hasattr(session.codex_stdin, 'sendall'):
                session.codex_stdin.sendall(formatted_message.encode('utf-8'))
            elif hasattr(session.codex_stdin, 'write'):
                session.codex_stdin.write(formatted_message.encode('utf-8'))
                if hasattr(session.codex_stdin, 'flush'):
                    session.codex_stdin.flush()
            else:
                raise Exception("No valid stdin stream available")

            # Read response
            response = await self._read_interactive_response(session, timeout)

            # Record response in history
            session.conversation_history.append({
                "type": "codex_response",
                "message": response,
                "timestamp": time.time(),
                "execution_time": time.time() - start_time
            })

            session.last_interaction = time.time()

            logger.info("Interactive message processed successfully",
                       session_id=session_id,
                       response_length=len(response),
                       execution_time=time.time() - start_time)

            return response

        except Exception as e:
            logger.error("Failed to process interactive message",
                        session_id=session_id,
                        error=str(e))
            raise

    async def _read_interactive_response(
        self,
        session: InteractiveSession,
        timeout: int
    ) -> str:
        """Read response from interactive Codex CLI session."""
        response_parts = []
        start_time = time.time()
        last_data_time = time.time()

        try:
            while time.time() - start_time < timeout:
                try:
                    # Try to read from stdout
                    if hasattr(session.codex_stdout, 'recv'):
                        # Socket-based reading
                        session.codex_stdout.settimeout(1.0)
                        data = session.codex_stdout.recv(4096)
                        if data:
                            response_parts.append(data.decode('utf-8', errors='ignore'))
                            last_data_time = time.time()
                    elif hasattr(session.codex_stdout, 'read'):
                        # Stream-based reading
                        data = session.codex_stdout.read(4096)
                        if data:
                            response_parts.append(data.decode('utf-8', errors='ignore'))
                            last_data_time = time.time()

                except (BlockingIOError, TimeoutError, OSError):
                    # No data available, continue waiting
                    pass

                # Check if response looks complete
                current_response = ''.join(response_parts)
                if current_response and self._is_response_complete(current_response):
                    break

                # Break if no activity for 5 seconds
                if time.time() - last_data_time > 5:
                    logger.debug("Response timeout - no new data",
                               session_id=session.session_id)
                    break

                await asyncio.sleep(0.1)

        except Exception as e:
            logger.error("Error reading interactive response",
                        session_id=session.session_id,
                        error=str(e))

        response = ''.join(response_parts).strip()

        if not response:
            response = "Codex CLI did not provide a response within the timeout period."

        return response

    def _is_response_complete(self, response: str) -> bool:
        """Check if response appears complete."""
        if not response:
            return False

        response_lower = response.lower().strip()

        # Look for completion indicators
        completion_patterns = [
            "anything else",
            "how can i help",
            "what would you like",
            "ready for the next",
            "let me know if",
            "is there something else"
        ]

        for pattern in completion_patterns:
            if pattern in response_lower:
                return True

        # Check for substantial content with proper ending
        if len(response) > 50 and response.rstrip().endswith(('.', '!', '?', ':')):
            return True

        return False

    async def end_interactive_session(self, session_id: str) -> None:
        """End an interactive Codex CLI session."""
        session = self.active_sessions.get(session_id)
        if not session:
            return

        logger.info("Ending interactive Codex CLI session",
                   session_id=session_id,
                   conversation_length=len(session.conversation_history))

        try:
            # Send exit command
            if session.codex_stdin:
                try:
                    exit_cmd = "exit\n"
                    if hasattr(session.codex_stdin, 'sendall'):
                        session.codex_stdin.sendall(exit_cmd.encode('utf-8'))
                    elif hasattr(session.codex_stdin, 'write'):
                        session.codex_stdin.write(exit_cmd.encode('utf-8'))
                        if hasattr(session.codex_stdin, 'flush'):
                            session.codex_stdin.flush()
                except Exception:
                    pass  # Ignore errors during cleanup

                # Close streams
                try:
                    if hasattr(session.codex_stdin, 'close'):
                        session.codex_stdin.close()
                    if hasattr(session.codex_stdout, 'close'):
                        session.codex_stdout.close()
                    if hasattr(session.codex_stderr, 'close'):
                        session.codex_stderr.close()
                except Exception:
                    pass

            # Clear session state
            session.conversation_active = False
            session.codex_process = None
            session.codex_stdin = None
            session.codex_stdout = None
            session.codex_stderr = None

            # Remove from active sessions
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]

            logger.info("Interactive Codex CLI session ended",
                       session_id=session_id)

        except Exception as e:
            logger.error("Error ending interactive session",
                        session_id=session_id,
                        error=str(e))

    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get information about an interactive session."""
        session = self.active_sessions.get(session_id)
        if not session:
            return None

        return {
            "session_id": session.session_id,
            "agent_id": session.agent_id,
            "conversation_active": session.conversation_active,
            "last_interaction": session.last_interaction,
            "conversation_length": len(session.conversation_history),
            "workspace_context_initialized": session.workspace_context_initialized,
            "client_workspace_dir": session.client_workspace_dir
        }

    def list_active_sessions(self) -> List[Dict[str, Any]]:
        """List all active interactive sessions."""
        return [
            self.get_session_info(session_id)
            for session_id in self.active_sessions.keys()
        ]