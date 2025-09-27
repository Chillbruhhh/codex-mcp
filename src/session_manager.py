"""
Session manager for agent isolation and lifecycle management.

This module handles the high-level session management for AI agents,
coordinating container creation, resource allocation, and cleanup
policies. Each agent gets completely isolated sessions with their
own Codex CLI instances.
"""

import asyncio
import time
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from contextlib import asynccontextmanager

import structlog

from .container_manager import CodexContainerManager, ContainerSession
from .utils.config import Config, get_config
from .utils.logging import LogContext
from .workspace_detector import workspace_detector

logger = structlog.get_logger(__name__)


@dataclass
class SessionMetrics:
    """Session performance and usage metrics."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_execution_time: float = 0.0
    average_execution_time: float = 0.0
    last_activity: float = field(default_factory=time.time)


@dataclass
class AgentSession:
    """High-level agent session with container and metrics."""
    session_id: str
    agent_id: str
    created_at: float
    last_activity: float
    status: str = "active"
    container_session: Optional[ContainerSession] = None
    metrics: SessionMetrics = field(default_factory=SessionMetrics)
    config: Dict[str, Any] = field(default_factory=dict)


class SessionTimeoutError(Exception):
    """Raised when session operations timeout."""
    pass


class SessionLimitError(Exception):
    """Raised when session limits are exceeded."""
    pass


class CodexSessionManager:
    """
    High-level session manager for AI agents.

    Coordinates container lifecycle, resource management, cleanup policies,
    and provides session isolation guarantees. Each agent gets completely
    isolated Codex CLI instances with their own configuration and workspace.
    """

    def __init__(self, config: Optional[Config] = None):
        """
        Initialize the session manager.

        Args:
            config: Optional configuration object
        """
        self.config = config or get_config()
        self.container_manager = CodexContainerManager(self.config)
        self.active_sessions: Dict[str, AgentSession] = {}
        self.agent_sessions: Dict[str, Set[str]] = {}  # agent_id -> session_ids
        self._cleanup_task: Optional[asyncio.Task] = None
        self._cleanup_started = False

        logger.info("Session manager initialized",
                   session_timeout=self.config.server.session_timeout,
                   max_sessions=self.config.server.max_concurrent_sessions)

    def _start_cleanup_task(self) -> None:
        """Start the periodic cleanup task (only if event loop is running)."""
        try:
            if not self._cleanup_started:
                self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
                self._cleanup_started = True
        except RuntimeError:
            # No event loop running - cleanup will start when needed
            pass

    async def _periodic_cleanup(self) -> None:
        """Periodically clean up expired sessions."""
        while True:
            try:
                await self._cleanup_expired_sessions()
                await asyncio.sleep(60)  # Check every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Cleanup task error", error=str(e))
                await asyncio.sleep(60)

    async def _cleanup_expired_sessions(self) -> None:
        """Clean up sessions that have exceeded the timeout."""
        current_time = time.time()
        expired_sessions = []

        for session_id, session in self.active_sessions.items():
            if (current_time - session.last_activity) > self.config.server.session_timeout:
                expired_sessions.append(session_id)

        for session_id in expired_sessions:
            logger.info("Cleaning up expired session",
                       session_id=session_id,
                       age_seconds=current_time - self.active_sessions[session_id].last_activity)
            await self.end_session(session_id)

    @asynccontextmanager
    async def create_session(
        self,
        agent_id: str,
        session_config: Optional[Dict[str, Any]] = None
    ):
        """
        Create a new agent session with isolated Codex CLI container.

        Args:
            agent_id: Unique identifier for the agent
            session_config: Optional session configuration

        Yields:
            AgentSession: Active session object

        Raises:
            SessionLimitError: If session limits are exceeded
        """
        session_id = f"session_{agent_id}_{int(time.time() * 1000)}"

        with LogContext(session_id):
            logger.info("Creating agent session",
                       session_id=session_id,
                       agent_id=agent_id)

            # Start cleanup task if not already started
            if not self._cleanup_started:
                self._start_cleanup_task()

            # Check session limits
            if len(self.active_sessions) >= self.config.server.max_concurrent_sessions:
                raise SessionLimitError(
                    f"Maximum sessions ({self.config.server.max_concurrent_sessions}) reached"
                )

            # Create session object
            current_time = time.time()
            session = AgentSession(
                session_id=session_id,
                agent_id=agent_id,
                created_at=current_time,
                last_activity=current_time,
                config=session_config or {}
            )

            try:
                # Extract Codex configuration
                model = session.config.get("model", self.config.codex.model)
                provider = session.config.get("provider", self.config.codex.provider)
                approval_mode = session.config.get("approval_mode", self.config.codex.approval_mode)

                # Detect client workspace for direct file collaboration
                client_workspace = workspace_detector.detect_client_workspace(
                    session_id=session_id,
                    hints=session.config.get("workspace_hints")
                )

                if client_workspace:
                    workspace_info = workspace_detector.get_workspace_info(client_workspace)
                    logger.info("Detected client workspace for collaborative session",
                               session_id=session_id,
                               workspace=client_workspace,
                               project_types=workspace_info.get("project_types", []),
                               has_git=workspace_info.get("has_git", False))

                # Create container session with workspace integration
                async with self.container_manager.create_session(
                    session_id=session_id,
                    agent_id=agent_id,
                    model=model,
                    provider=provider,
                    approval_mode=approval_mode,
                    client_workspace_dir=client_workspace  # Pass detected workspace
                ) as container_session:

                    session.container_session = container_session
                    session.status = "active"

                    # Register session
                    self.active_sessions[session_id] = session
                    if agent_id not in self.agent_sessions:
                        self.agent_sessions[agent_id] = set()
                    self.agent_sessions[agent_id].add(session_id)

                    logger.info("Agent session created successfully",
                               session_id=session_id,
                               agent_id=agent_id,
                               container_id=container_session.container_id)

                    yield session

            except Exception as e:
                logger.error("Failed to create agent session",
                           session_id=session_id,
                           error=str(e))
                session.status = "failed"
                raise

            finally:
                # Cleanup when context exits
                await self._cleanup_session(session_id)

    async def create_persistent_session(
        self,
        agent_id: str,
        session_config: Optional[Dict[str, Any]] = None
    ) -> AgentSession:
        """
        Create a persistent agent session that remains active until explicitly ended.

        This method creates a session that doesn't auto-cleanup when the context exits,
        making it suitable for MCP tools that need to create a session and use it later.

        Args:
            agent_id: Unique identifier for the agent
            session_config: Optional session configuration

        Returns:
            AgentSession: Active session object

        Raises:
            SessionLimitError: If session limits are exceeded
        """
        session_id = f"session_{agent_id}_{int(time.time() * 1000)}"

        with LogContext(session_id):
            logger.info("Creating persistent agent session",
                       session_id=session_id,
                       agent_id=agent_id)

            # Start cleanup task if not already started
            if not self._cleanup_started:
                self._start_cleanup_task()

            # Check session limits
            if len(self.active_sessions) >= self.config.server.max_concurrent_sessions:
                raise SessionLimitError(
                    f"Maximum sessions ({self.config.server.max_concurrent_sessions}) reached"
                )

            # Create session object
            current_time = time.time()
            session = AgentSession(
                session_id=session_id,
                agent_id=agent_id,
                created_at=current_time,
                last_activity=current_time,
                config=session_config or {}
            )

            try:
                # Extract Codex configuration
                model = session.config.get("model", self.config.codex.model)
                provider = session.config.get("provider", self.config.codex.provider)
                approval_mode = session.config.get("approval_mode", self.config.codex.approval_mode)

                # Detect client workspace for persistent collaborative session
                client_workspace = workspace_detector.detect_client_workspace(
                    session_id=session_id,
                    hints=session.config.get("workspace_hints")
                )

                if client_workspace:
                    workspace_info = workspace_detector.get_workspace_info(client_workspace)
                    logger.info("Detected client workspace for persistent session",
                               session_id=session_id,
                               workspace=client_workspace,
                               project_types=workspace_info.get("project_types", []),
                               has_git=workspace_info.get("has_git", False))

                # Create container session directly (no context manager) with workspace
                container_session = await self.container_manager._create_persistent_session(
                    session_id=session_id,
                    agent_id=agent_id,
                    model=model,
                    provider=provider,
                    approval_mode=approval_mode,
                    client_workspace_dir=client_workspace  # Pass detected workspace
                )

                session.container_session = container_session
                session.status = "active"

                # Register session
                self.active_sessions[session_id] = session
                if agent_id not in self.agent_sessions:
                    self.agent_sessions[agent_id] = set()
                self.agent_sessions[agent_id].add(session_id)

                logger.info("Persistent agent session created successfully",
                           session_id=session_id,
                           agent_id=agent_id,
                           container_id=container_session.container_id)

                return session

            except Exception as e:
                logger.error("Failed to create persistent agent session",
                           session_id=session_id,
                           error=str(e))
                session.status = "failed"
                # Clean up the failed session attempt
                if session_id in self.active_sessions:
                    del self.active_sessions[session_id]
                raise

    async def get_or_create_active_session(
        self,
        agent_id: str,
        session_config: Optional[Dict[str, Any]] = None,
    ) -> AgentSession:
        """Return an existing active session or create a new persistent one."""

        # Prefer an existing active session to maintain conversation context
        for session_id in await self.get_agent_sessions(agent_id):
            session = self.active_sessions.get(session_id)
            if session and session.status == "active":
                return session

        # No active session found; create a new persistent one
        return await self.create_persistent_session(
            agent_id=agent_id,
            session_config=session_config,
        )
    async def send_message_to_codex(
        self,
        session_id: str,
        message: str,
        timeout: int = 300
    ) -> str:
        """
        Send a natural language message to Codex CLI in the specified session.

        Args:
            session_id: Session identifier
            message: Natural language message to send
            timeout: Response timeout in seconds

        Returns:
            str: Codex CLI response

        Raises:
            ValueError: If session not found
            SessionTimeoutError: If message times out
        """
        session = self.active_sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        if not session.container_session:
            raise ValueError(f"Session {session_id} has no active container")

        with LogContext(session_id):
            start_time = time.time()

            try:
                # Update last activity
                session.last_activity = time.time()
                session.metrics.total_requests += 1

                # Send message to Codex
                response = await self.container_manager.send_message_to_codex(
                    session.container_session,
                    message,
                    timeout
                )

                # Update metrics
                execution_time = time.time() - start_time
                session.metrics.total_execution_time += execution_time
                session.metrics.average_execution_time = (
                    session.metrics.total_execution_time / session.metrics.total_requests
                )

                session.metrics.successful_requests += 1

                logger.info("Codex message sent successfully",
                           session_id=session_id,
                           message_preview=message[:50],
                           response_length=len(response),
                           execution_time=execution_time)

                return response

            except asyncio.TimeoutError:
                session.metrics.failed_requests += 1
                logger.error("Codex message timeout",
                           session_id=session_id,
                           message_preview=message[:50],
                           timeout=timeout)
                raise SessionTimeoutError(f"Message timed out after {timeout} seconds")

            except Exception as e:
                session.metrics.failed_requests += 1
                logger.error("Codex message failed",
                           session_id=session_id,
                           message_preview=message[:50],
                           error=str(e))
                raise

    async def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a session.

        Args:
            session_id: Session identifier

        Returns:
            Dict[str, Any]: Session information or None if not found
        """
        session = self.active_sessions.get(session_id)
        if not session:
            return None

        info = {
            "session_id": session.session_id,
            "agent_id": session.agent_id,
            "status": session.status,
            "created_at": session.created_at,
            "last_activity": session.last_activity,
            "age_seconds": time.time() - session.created_at,
            "idle_seconds": time.time() - session.last_activity,
            "config": session.config,
            "metrics": {
                "total_requests": session.metrics.total_requests,
                "successful_requests": session.metrics.successful_requests,
                "failed_requests": session.metrics.failed_requests,
                "success_rate": (
                    session.metrics.successful_requests / session.metrics.total_requests
                    if session.metrics.total_requests > 0 else 0.0
                ),
                "average_execution_time": session.metrics.average_execution_time,
                "total_execution_time": session.metrics.total_execution_time
            }
        }

        # Add container information if available
        if session.container_session:
            container_info = await self.container_manager.get_session_info(session_id)
            if container_info:
                info["container"] = container_info

        return info

    async def list_sessions(
        self,
        agent_id: Optional[str] = None,
        include_metrics: bool = True
    ) -> List[Dict[str, Any]]:
        """
        List active sessions, optionally filtered by agent.

        Args:
            agent_id: Optional agent ID filter
            include_metrics: Whether to include detailed metrics

        Returns:
            List[Dict[str, Any]]: List of session information
        """
        sessions = []

        session_ids = (
            self.agent_sessions.get(agent_id, set()) if agent_id
            else set(self.active_sessions.keys())
        )

        for session_id in session_ids:
            if include_metrics:
                session_info = await self.get_session_info(session_id)
                if session_info:
                    sessions.append(session_info)
            else:
                session = self.active_sessions.get(session_id)
                if session:
                    sessions.append({
                        "session_id": session.session_id,
                        "agent_id": session.agent_id,
                        "status": session.status,
                        "created_at": session.created_at,
                        "last_activity": session.last_activity
                    })

        return sessions

    async def end_session(self, session_id: str) -> bool:
        """
        Terminate a session and clean up resources.

        Args:
            session_id: Session identifier

        Returns:
            bool: True if session was found and terminated
        """
        session = self.active_sessions.get(session_id)
        if not session:
            return False

        with LogContext(session_id):
            logger.info("Ending session", session_id=session_id)
            await self._cleanup_session(session_id)
            return True

    async def _cleanup_session(self, session_id: str) -> None:
        """Clean up session resources with proper container coordination."""
        session = self.active_sessions.get(session_id)
        if not session:
            return

        try:
            # First, clean up the container resources through the container manager
            if session.container_session:
                try:
                    await self.container_manager._cleanup_session(session.container_session)
                    logger.debug("Container cleanup completed",
                               session_id=session_id)
                except Exception as e:
                    logger.warning("Container cleanup failed during session cleanup",
                                 session_id=session_id,
                                 error=str(e))

            # Then remove from session tracking
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]

            if session.agent_id in self.agent_sessions:
                self.agent_sessions[session.agent_id].discard(session_id)
                if not self.agent_sessions[session.agent_id]:
                    del self.agent_sessions[session.agent_id]

            session.status = "terminated"

            logger.info("Session cleaned up completely",
                       session_id=session_id,
                       final_metrics=session.metrics)

        except Exception as e:
            logger.error("Session cleanup error",
                        session_id=session_id,
                        error=str(e))

    async def get_agent_sessions(self, agent_id: str) -> List[str]:
        """
        Get all session IDs for a specific agent.

        Args:
            agent_id: Agent identifier

        Returns:
            List[str]: List of session IDs
        """
        return list(self.agent_sessions.get(agent_id, set()))

    async def get_system_stats(self) -> Dict[str, Any]:
        """
        Get system-wide session statistics.

        Returns:
            Dict[str, Any]: System statistics
        """
        current_time = time.time()
        total_requests = sum(s.metrics.total_requests for s in self.active_sessions.values())
        total_successes = sum(s.metrics.successful_requests for s in self.active_sessions.values())

        stats = {
            "total_active_sessions": len(self.active_sessions),
            "total_agents": len(self.agent_sessions),
            "max_sessions": self.config.server.max_concurrent_sessions,
            "session_timeout": self.config.server.session_timeout,
            "total_requests": total_requests,
            "total_successful_requests": total_successes,
            "overall_success_rate": total_successes / total_requests if total_requests > 0 else 0.0,
            "oldest_session_age": (
                min(current_time - s.created_at for s in self.active_sessions.values())
                if self.active_sessions else 0
            ),
            "newest_session_age": (
                max(current_time - s.created_at for s in self.active_sessions.values())
                if self.active_sessions else 0
            )
        }

        return stats

    async def shutdown(self) -> None:
        """
        Gracefully shutdown the session manager.

        Cleans up all active sessions and stops background tasks.
        """
        logger.info("Shutting down session manager",
                   active_sessions=len(self.active_sessions))

        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Clean up all sessions
        if self.active_sessions:
            session_ids = list(self.active_sessions.keys())
            cleanup_tasks = [self._cleanup_session(sid) for sid in session_ids]
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)

        # Cleanup container manager
        await self.container_manager.cleanup_all_sessions()

        logger.info("Session manager shutdown complete")

    def __del__(self):
        """Ensure cleanup on destruction."""
        try:
            if hasattr(self, 'active_sessions') and self.active_sessions:
                logger.warning("Session manager destroyed with active sessions",
                             count=len(self.active_sessions))
        except Exception:
            pass
