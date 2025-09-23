"""
Test suite for the MCP server implementation.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from src.mcp_server import (
    create_mcp_server,
    health_check,
    list_sessions,
    codex_chat,
    create_codex_session,
    end_codex_session
)


class TestMCPServer:
    """Test cases for MCP server functionality."""

    def test_create_mcp_server(self):
        """Test server creation."""
        server = create_mcp_server()
        assert server is not None
        assert server.name == "Codex CLI MCP Server"
        assert server.version == "0.1.0"

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test health check tool."""
        result = await health_check()

        assert result.status == "healthy"
        assert result.version == "0.1.0"
        assert result.uptime_seconds >= 0
        assert result.active_sessions >= 0
        assert result.timestamp is not None

    @pytest.mark.asyncio
    async def test_list_sessions(self):
        """Test session listing."""
        result = await list_sessions()

        assert "total_sessions" in result
        assert "sessions" in result
        assert isinstance(result["sessions"], list)

    @pytest.mark.asyncio
    async def test_create_codex_session(self):
        """Test session creation."""
        agent_id = "test_agent_123"
        result = await create_codex_session(agent_id)

        assert result["agent_id"] == agent_id
        assert result["status"] == "created"
        assert "session_id" in result
        assert result["session_id"].startswith(f"session_{agent_id}")

    @pytest.mark.asyncio
    async def test_codex_chat_placeholder(self):
        """Test chat functionality (placeholder implementation)."""
        message = "Hello, Codex!"
        result = await codex_chat(message)

        assert "[PLACEHOLDER]" in result
        assert message in result

    @pytest.mark.asyncio
    async def test_end_session(self):
        """Test session termination."""
        # First create a session
        agent_id = "test_agent_456"
        create_result = await create_codex_session(agent_id)
        session_id = create_result["session_id"]

        # Then end it
        end_result = await end_codex_session(session_id)

        assert end_result["status"] == "terminated"
        assert end_result["session_id"] == session_id

    @pytest.mark.asyncio
    async def test_end_nonexistent_session(self):
        """Test ending a session that doesn't exist."""
        result = await end_codex_session("nonexistent_session")

        assert result["status"] == "error"
        assert "not found" in result["message"]


@pytest.mark.asyncio
async def test_server_tools_registration():
    """Test that all tools are properly registered."""
    server = create_mcp_server()

    # Check that tools are registered
    tools = server._tools
    tool_names = [tool.name for tool in tools.values()]

    expected_tools = [
        "health_check",
        "list_sessions",
        "codex_chat",
        "codex_generate_code",
        "create_codex_session",
        "end_codex_session"
    ]

    for tool_name in expected_tools:
        assert tool_name in tool_names, f"Tool {tool_name} not registered"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])