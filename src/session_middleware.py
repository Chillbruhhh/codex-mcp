"""
MCP Session Detection Middleware for FastMCP.

This module provides middleware to detect and track MCP client sessions,
enabling session-aware agent container management. It integrates with
FastMCP's session system to automatically manage agent lifecycles.
"""

import asyncio
import functools
from typing import Optional, Any, Callable, Dict
from contextlib import contextmanager
import structlog

from .session_registry import get_session_registry, MCPSessionRegistry

logger = structlog.get_logger(__name__)

# Thread-local storage for current session context
import threading
_session_context = threading.local()


class MCPSessionContext:
    """Context manager for MCP session information."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.session_registry = get_session_registry()

    async def __aenter__(self):
        """Async context manager entry."""
        # Store session ID in thread-local storage
        _session_context.current_session_id = self.session_id

        # Register session activity
        await self.session_registry.get_or_create_session_agent(self.session_id)

        logger.debug("Entered MCP session context", session_id=self.session_id)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        # Clear session context
        if hasattr(_session_context, 'current_session_id'):
            delattr(_session_context, 'current_session_id')

        logger.debug("Exited MCP session context", session_id=self.session_id)


def get_current_mcp_session_id() -> Optional[str]:
    """
    Get the current MCP session ID from context.

    Returns:
        Current MCP session ID or None if not in session context
    """
    return getattr(_session_context, 'current_session_id', None)


def session_aware_tool(func: Callable) -> Callable:
    """
    Decorator to make MCP tools session-aware.

    This decorator automatically injects session context into tool functions,
    enabling them to use session-scoped agent containers.

    Args:
        func: The tool function to decorate

    Returns:
        Decorated function with session awareness
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        """Wrapper that provides session context."""
        # Try to extract session ID from current context
        session_id = extract_session_id_from_context()

        if session_id is None:
            # Fallback to default agent if no session context
            logger.warning("No MCP session context found, using fallback session",
                          function=func.__name__)
            session_id = "fallback_session"

        # Create session context for this tool execution
        async with create_session_context(session_id):
            logger.debug("Executing session-aware tool",
                        function=func.__name__,
                        session_id=session_id)

            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error("Session-aware tool execution failed",
                            function=func.__name__,
                            session_id=session_id,
                            error=str(e))
                raise

    return wrapper


def extract_session_id_from_context() -> Optional[str]:
    """
    Extract session ID from various context sources.

    This function tries multiple strategies to get a session identifier:
    1. Thread-local storage (if already set)
    2. FastMCP request context
    3. HTTP headers (if available)
    4. Generate fallback ID

    Returns:
        Session ID if found or generated
    """
    # First check if we already have a session ID in context
    current_id = get_current_mcp_session_id()
    if current_id:
        return current_id

    # Try to extract from FastMCP context
    session_id = FastMCPSessionExtractor.extract_session_id()
    if session_id:
        return session_id

    # If all else fails, return None and let the caller handle it
    return None


class FastMCPSessionExtractor:
    """
    Extracts session information from FastMCP requests.

    This class provides utilities to extract session identifiers from
    various parts of FastMCP requests and contexts.
    """

    @staticmethod
    def extract_from_request_context() -> Optional[str]:
        """
        Extract session ID from FastMCP request context.

        For FastMCP 2.0 with SSE transport, session information is managed
        internally. We extract it from the SSE connection context.

        Returns:
            Session ID if found, None otherwise
        """
        try:
            # For SSE transport, each connection is a session
            # We'll generate a consistent session ID based on connection info
            import socket
            import hashlib

            # Try to get some connection-unique identifier
            # This is a simplified approach - in production you'd want
            # to properly integrate with FastMCP's session management
            connection_info = f"{socket.gethostname()}_{threading.current_thread().ident}"
            session_id = hashlib.md5(connection_info.encode()).hexdigest()[:16]

            logger.debug("Generated session ID from connection context", session_id=session_id)
            return session_id

        except Exception as e:
            logger.debug("Could not extract session from connection context", error=str(e))

        return None

    @staticmethod
    def extract_from_headers(headers: Dict[str, str]) -> Optional[str]:
        """
        Extract session ID from HTTP headers.

        Args:
            headers: HTTP request headers

        Returns:
            Session ID if found in headers
        """
        # Check common session header names
        session_headers = [
            'x-session-id',
            'session-id',
            'x-mcp-session',
            'mcp-session-id'
        ]

        for header in session_headers:
            if header in headers:
                return headers[header]

        return None

    @staticmethod
    def extract_from_url_params(url: str) -> Optional[str]:
        """
        Extract session ID from URL parameters.

        Args:
            url: Request URL

        Returns:
            Session ID if found in URL
        """
        try:
            from urllib.parse import urlparse, parse_qs

            parsed = urlparse(url)
            params = parse_qs(parsed.query)

            session_params = ['session_id', 'sessionId', 'mcp_session']

            for param in session_params:
                if param in params and params[param]:
                    return params[param][0]

        except Exception as e:
            logger.debug("Could not extract session from URL", error=str(e))

        return None

    @classmethod
    def extract_session_id(cls, **context) -> str:
        """
        Extract session ID from available context information.

        This method tries multiple strategies to get a session identifier,
        falling back to generating one if necessary.

        Args:
            **context: Context information (headers, url, etc.)

        Returns:
            Session ID (extracted or generated)
        """
        # Try FastMCP context first
        session_id = cls.extract_from_request_context()
        if session_id:
            return session_id

        # Try headers
        headers = context.get('headers', {})
        session_id = cls.extract_from_headers(headers)
        if session_id:
            return session_id

        # Try URL parameters
        url = context.get('url', '')
        session_id = cls.extract_from_url_params(url)
        if session_id:
            return session_id

        # Generate fallback session ID
        import uuid
        fallback_id = str(uuid.uuid4())
        logger.debug("Generated fallback session ID", session_id=fallback_id)
        return fallback_id


async def get_session_agent_id() -> str:
    """
    Get the agent ID for the current MCP session.

    Returns:
        Agent ID for the current session
    """
    session_id = get_current_mcp_session_id()
    if session_id is None:
        # If no session context, try to extract it
        session_id = FastMCPSessionExtractor.extract_session_id()

    session_registry = get_session_registry()
    agent_id = await session_registry.get_or_create_session_agent(session_id)

    logger.debug("Retrieved session agent ID",
                session_id=session_id,
                agent_id=agent_id)

    return agent_id


def create_session_context(session_id: str) -> MCPSessionContext:
    """
    Create a new MCP session context.

    Args:
        session_id: MCP session identifier

    Returns:
        MCPSessionContext for use with async context manager
    """
    return MCPSessionContext(session_id)


# Global session cleanup handler
async def cleanup_session_on_disconnect(session_id: str):
    """
    Handle cleanup when an MCP session disconnects.

    Args:
        session_id: Session identifier to clean up
    """
    session_registry = get_session_registry()
    agent_id = await session_registry.end_session(session_id)

    if agent_id:
        logger.info("MCP session disconnected, cleaning up agent",
                   session_id=session_id,
                   agent_id=agent_id)

        # TODO: Trigger container cleanup
        # This will be implemented when we integrate with container manager
        return agent_id

    return None