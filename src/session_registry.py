"""
MCP Session Registry for tracking client sessions and agent containers.

This module provides session-aware management of agent containers, ensuring
that each MCP client session gets its own persistent Codex CLI container
that maintains state throughout the session lifecycle.
"""

import asyncio
import time
from typing import Dict, Optional, Set
from dataclasses import dataclass, field
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class MCPSessionInfo:
    """Information about an active MCP session."""
    session_id: str
    agent_id: str
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    container_id: Optional[str] = None
    active: bool = True


class MCPSessionRegistry:
    """
    Registry for tracking MCP client sessions and their associated agent containers.

    This class manages the mapping between MCP client sessions and persistent
    agent containers, ensuring proper lifecycle management and cleanup.
    """

    def __init__(self, session_timeout: int = 3600):
        """
        Initialize the session registry.

        Args:
            session_timeout: Session timeout in seconds (default: 1 hour)
        """
        self.session_timeout = session_timeout
        self.sessions: Dict[str, MCPSessionInfo] = {}
        self.agent_to_session: Dict[str, str] = {}
        self.cleanup_lock = asyncio.Lock()

        # Start background cleanup task
        self._cleanup_task = None
        self._start_cleanup_task()

    def _start_cleanup_task(self):
        """Start the background cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self):
        """Background task to clean up stale sessions."""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes
                await self.cleanup_stale_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in session cleanup loop", error=str(e))

    async def get_or_create_session_agent(self, mcp_session_id: str) -> str:
        """
        Get the agent ID for an MCP session, creating one if needed.

        Args:
            mcp_session_id: MCP client session identifier

        Returns:
            str: Agent ID for this session
        """
        if mcp_session_id in self.sessions:
            # Update last activity
            self.sessions[mcp_session_id].last_activity = time.time()
            agent_id = self.sessions[mcp_session_id].agent_id

            logger.debug("Using existing session agent",
                        mcp_session_id=mcp_session_id,
                        agent_id=agent_id)
            return agent_id

        # Create new session
        agent_id = f"mcp_session_{mcp_session_id}"
        session_info = MCPSessionInfo(
            session_id=mcp_session_id,
            agent_id=agent_id
        )

        self.sessions[mcp_session_id] = session_info
        self.agent_to_session[agent_id] = mcp_session_id

        logger.info("Created new session agent mapping",
                   mcp_session_id=mcp_session_id,
                   agent_id=agent_id)

        return agent_id

    def update_container_id(self, mcp_session_id: str, container_id: str):
        """
        Update the container ID for a session.

        Args:
            mcp_session_id: MCP session identifier
            container_id: Docker container ID
        """
        if mcp_session_id in self.sessions:
            self.sessions[mcp_session_id].container_id = container_id
            logger.debug("Updated session container ID",
                        mcp_session_id=mcp_session_id,
                        container_id=container_id[:12])

    def get_session_info(self, mcp_session_id: str) -> Optional[MCPSessionInfo]:
        """
        Get session information.

        Args:
            mcp_session_id: MCP session identifier

        Returns:
            MCPSessionInfo or None if session doesn't exist
        """
        return self.sessions.get(mcp_session_id)

    def get_agent_session(self, agent_id: str) -> Optional[str]:
        """
        Get the MCP session ID for an agent.

        Args:
            agent_id: Agent identifier

        Returns:
            MCP session ID or None if not found
        """
        return self.agent_to_session.get(agent_id)

    async def end_session(self, mcp_session_id: str) -> Optional[str]:
        """
        End an MCP session and return the agent ID for cleanup.

        Args:
            mcp_session_id: MCP session identifier

        Returns:
            Agent ID if session existed, None otherwise
        """
        async with self.cleanup_lock:
            if mcp_session_id not in self.sessions:
                return None

            session_info = self.sessions[mcp_session_id]
            agent_id = session_info.agent_id

            # Mark as inactive
            session_info.active = False

            # Remove from mappings
            del self.sessions[mcp_session_id]
            if agent_id in self.agent_to_session:
                del self.agent_to_session[agent_id]

            logger.info("Ended MCP session",
                       mcp_session_id=mcp_session_id,
                       agent_id=agent_id,
                       container_id=session_info.container_id[:12] if session_info.container_id else None)

            return agent_id

    async def cleanup_stale_sessions(self) -> int:
        """
        Clean up sessions that have been inactive for too long.

        Returns:
            Number of sessions cleaned up
        """
        async with self.cleanup_lock:
            current_time = time.time()
            stale_sessions = []

            for session_id, session_info in self.sessions.items():
                if current_time - session_info.last_activity > self.session_timeout:
                    stale_sessions.append(session_id)

            cleaned_count = 0
            for session_id in stale_sessions:
                agent_id = await self.end_session(session_id)
                if agent_id:
                    cleaned_count += 1
                    logger.info("Cleaned up stale session",
                               session_id=session_id,
                               agent_id=agent_id,
                               inactive_duration=current_time - self.sessions.get(session_id, MCPSessionInfo("", "")).last_activity)

            return cleaned_count

    def get_active_sessions(self) -> Dict[str, MCPSessionInfo]:
        """
        Get all active sessions.

        Returns:
            Dictionary of active session information
        """
        return {sid: info for sid, info in self.sessions.items() if info.active}

    def get_session_count(self) -> int:
        """Get the number of active sessions."""
        return len([s for s in self.sessions.values() if s.active])

    async def shutdown(self):
        """Shutdown the session registry and cleanup resources."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        logger.info("Session registry shutdown complete")


# Global session registry instance
_session_registry: Optional[MCPSessionRegistry] = None


def get_session_registry() -> MCPSessionRegistry:
    """Get the global session registry instance."""
    global _session_registry
    if _session_registry is None:
        _session_registry = MCPSessionRegistry()
    return _session_registry


def reset_session_registry():
    """Reset the global session registry (for testing)."""
    global _session_registry
    if _session_registry:
        asyncio.create_task(_session_registry.shutdown())
    _session_registry = None