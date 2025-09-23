#!/usr/bin/env python3
"""
STDIO-compatible MCP server for Codex CLI integration.

This server implements the MCP protocol directly over stdin/stdout for
compatibility with MCP Inspector and Claude Desktop. It uses the same
conversational tools as the FastMCP server but with native MCP transport.
"""

import asyncio
import json
import logging
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

# Configure logging to stderr BEFORE importing any modules
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Reconfigure structlog to use stderr
import structlog
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    logger_factory=structlog.WriteLoggerFactory(sys.stderr),
    cache_logger_on_first_use=True,
)

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.mcp_server import (
    mcp,
    session_manager,
    server_start_time
)
from src.mcp_server import (
    HealthCheckResponse,
    SessionInfo
)
import time
from datetime import datetime

logger = logging.getLogger(__name__)


# Wrapper functions for tools (since FastMCP 2.0 tools are decorated objects)
async def health_check_impl() -> HealthCheckResponse:
    """Implementation of health check for stdio server."""
    uptime = time.time() - server_start_time
    system_stats = await session_manager.get_system_stats()

    return HealthCheckResponse(
        status="healthy",
        version="0.1.0",
        uptime_seconds=uptime,
        active_sessions=system_stats["total_active_sessions"],
        timestamp=datetime.now().isoformat()
    )


async def list_sessions_impl(agent_id: Optional[str] = None) -> Dict[str, Any]:
    """Implementation of list sessions for stdio server."""
    sessions = await session_manager.list_sessions(agent_id=agent_id)

    return {
        "total_sessions": len(sessions),
        "sessions": sessions,
        "filtered_by_agent": agent_id
    }


async def codex_chat_impl(message: str, session_id: Optional[str] = None, agent_id: str = "default_agent") -> str:
    """Implementation of codex chat for stdio server."""
    from src.utils.logging import LogContext

    with LogContext(f"agent_{agent_id}"):
        logger.info("Processing chat message with persistent agent",
                   message_preview=message[:100],
                   agent_id=agent_id)

        try:
            container_manager = session_manager.container_manager

            # Get or create persistent container for this agent
            session = await container_manager.get_or_create_persistent_agent_container(
                agent_id=agent_id,
                model="gpt-5",
                provider="openai",
                approval_mode="suggest"
            )

            # Send message to the persistent container
            response = await container_manager.send_message_to_codex(
                session=session,
                message=message
            )

            logger.info("Persistent agent chat completed",
                       agent_id=agent_id,
                       response_length=len(response))

            return response

        except Exception as e:
            logger.error("Persistent agent chat failed",
                        agent_id=agent_id,
                        error=str(e))
            return f"Error communicating with persistent agent {agent_id}: {str(e)}"


async def codex_generate_code_impl(prompt: str, language: str = "python", session_id: Optional[str] = None, agent_id: str = "default_agent") -> str:
    """Implementation of codex generate code for stdio server."""
    # Construct natural language request for code generation
    code_request = f"Please generate {language} code for: {prompt}"

    try:
        if session_id:
            # Use existing session
            response = await session_manager.send_message_to_codex(
                session_id=session_id,
                message=code_request
            )
            return response
        else:
            # Create new session for code generation
            async with session_manager.create_session(agent_id=agent_id) as session:
                response = await session_manager.send_message_to_codex(
                    session_id=session.session_id,
                    message=code_request
                )
                return response

    except Exception as e:
        logger.error("Code generation failed", error=str(e))
        return f"Error generating code: {str(e)}"


async def create_codex_session_impl(agent_id: str, model: str = "gpt-5", provider: str = "openai", approval_mode: str = "suggest") -> Dict[str, str]:
    """Implementation of create codex session for stdio server."""
    try:
        session_config = {
            "model": model,
            "provider": provider,
            "approval_mode": approval_mode
        }

        # Create persistent session (will remain active until explicitly ended)
        session = await session_manager.create_persistent_session(
            agent_id=agent_id,
            session_config=session_config
        )

        session_info = await session_manager.get_session_info(session.session_id)

        return {
            "session_id": session.session_id,
            "agent_id": agent_id,
            "status": "created",
            "container_id": session_info.get("container", {}).get("container_id", ""),
            "message": "Session created successfully with isolated Codex CLI container"
        }

    except Exception as e:
        logger.error("Session creation failed",
                    agent_id=agent_id,
                    error=str(e))
        return {
            "session_id": "",
            "agent_id": agent_id,
            "status": "error",
            "message": f"Session creation failed: {str(e)}"
        }


async def get_auth_status_impl() -> Dict[str, Any]:
    """Implementation of get auth status for stdio server."""
    try:
        auth_info = session_manager.container_manager.auth_manager.get_auth_info()
        return {
            "status": "success",
            "authentication": auth_info,
            "message": "Authentication status retrieved successfully"
        }
    except Exception as e:
        logger.error("Failed to get auth status", error=str(e))
        return {
            "status": "error",
            "authentication": {
                "available_methods": {"api_key": False, "chatgpt_oauth": False},
                "status": "error"
            },
            "message": f"Failed to get authentication status: {str(e)}"
        }


async def end_codex_session_impl(session_id: str) -> Dict[str, str]:
    """Implementation of end codex session for stdio server."""
    try:
        success = await session_manager.end_session(session_id)

        if success:
            return {
                "session_id": session_id,
                "status": "terminated",
                "message": "Session terminated and all resources cleaned up successfully"
            }
        else:
            return {
                "session_id": session_id,
                "status": "error",
                "message": f"Session {session_id} not found"
            }

    except Exception as e:
        logger.error("Session termination failed",
                    session_id=session_id,
                    error=str(e))
        return {
            "session_id": session_id,
            "status": "error",
            "message": f"Session termination failed: {str(e)}"
        }


class StdioMCPServer:
    """MCP server with STDIO transport for Inspector/Claude Desktop compatibility."""

    def __init__(self):
        """Initialize the STDIO MCP server."""
        self.tools = {
            "health_check": {
                "name": "health_check",
                "description": "Check the health status of the Codex CLI MCP Server",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            "list_sessions": {
                "name": "list_sessions",
                "description": "List all active Codex CLI sessions",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "Optional agent ID to filter sessions"
                        }
                    },
                    "required": []
                }
            },
            "codex_chat": {
                "name": "codex_chat",
                "description": "Send a natural language message to Codex CLI in an isolated container",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "The natural language message to send to Codex CLI"
                        },
                        "session_id": {
                            "type": "string",
                            "description": "Optional session ID for session continuity"
                        },
                        "agent_id": {
                            "type": "string",
                            "description": "Agent identifier for session management",
                            "default": "default_agent"
                        }
                    },
                    "required": ["message"]
                }
            },
            "codex_generate_code": {
                "name": "codex_generate_code",
                "description": "Generate code using Codex CLI through natural language conversation",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "Description of the code to generate"
                        },
                        "language": {
                            "type": "string",
                            "description": "Programming language",
                            "default": "python"
                        },
                        "session_id": {
                            "type": "string",
                            "description": "Optional session ID for context continuity"
                        },
                        "agent_id": {
                            "type": "string",
                            "description": "Agent identifier for session management",
                            "default": "default_agent"
                        }
                    },
                    "required": ["prompt"]
                }
            },
            "create_codex_session": {
                "name": "create_codex_session",
                "description": "Create a new isolated Codex CLI session for an agent",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "Unique identifier for the requesting agent"
                        },
                        "model": {
                            "type": "string",
                            "description": "Codex model to use",
                            "default": "gpt-4"
                        },
                        "provider": {
                            "type": "string",
                            "description": "AI provider",
                            "default": "openai"
                        },
                        "approval_mode": {
                            "type": "string",
                            "description": "Codex approval mode",
                            "default": "suggest"
                        }
                    },
                    "required": ["agent_id"]
                }
            },
            "get_auth_status": {
                "name": "get_auth_status",
                "description": "Get authentication status and available methods",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            "end_codex_session": {
                "name": "end_codex_session",
                "description": "Terminate a Codex CLI session and cleanup resources",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "ID of the session to terminate"
                        }
                    },
                    "required": ["session_id"]
                }
            }
        }

        logger.info("STDIO MCP Server initialized")
        logger.info(f"Available tools: {len(self.tools)}")

    async def handle_initialize(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP initialize request."""
        logger.info("Handling initialize request")

        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "codex-cli-mcp-server",
                    "version": "0.1.0"
                }
            }
        }

    async def handle_list_tools(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/list request."""
        logger.info("Handling list_tools request")

        tools_list = [
            {
                "name": tool["name"],
                "description": tool["description"],
                "inputSchema": tool["inputSchema"]
            }
            for tool in self.tools.values()
        ]

        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "tools": tools_list
            }
        }

    async def handle_call_tool(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/call request."""
        params = request.get("params", {})
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        logger.info(f"Handling tool call: {tool_name}")

        try:
            # Route to appropriate tool function implementation
            if tool_name == "health_check":
                result = await health_check_impl()
                content = [{"type": "text", "text": json.dumps(result.model_dump(), indent=2)}]

            elif tool_name == "list_sessions":
                agent_id = arguments.get("agent_id")
                result = await list_sessions_impl(agent_id)
                content = [{"type": "text", "text": json.dumps(result, indent=2)}]

            elif tool_name == "codex_chat":
                message = arguments.get("message")
                session_id = arguments.get("session_id")
                agent_id = arguments.get("agent_id", "default_agent")

                if not message:
                    raise ValueError("message parameter is required")

                result = await codex_chat_impl(message, session_id, agent_id)
                content = [{"type": "text", "text": result}]

            elif tool_name == "codex_generate_code":
                prompt = arguments.get("prompt")
                language = arguments.get("language", "python")
                session_id = arguments.get("session_id")
                agent_id = arguments.get("agent_id", "default_agent")

                if not prompt:
                    raise ValueError("prompt parameter is required")

                result = await codex_generate_code_impl(prompt, language, session_id, agent_id)
                content = [{"type": "text", "text": result}]

            elif tool_name == "create_codex_session":
                agent_id = arguments.get("agent_id")
                model = arguments.get("model", "gpt-5")
                provider = arguments.get("provider", "openai")
                approval_mode = arguments.get("approval_mode", "suggest")

                if not agent_id:
                    raise ValueError("agent_id parameter is required")

                result = await create_codex_session_impl(agent_id, model, provider, approval_mode)
                content = [{"type": "text", "text": json.dumps(result, indent=2)}]

            elif tool_name == "get_auth_status":
                result = await get_auth_status_impl()
                content = [{"type": "text", "text": json.dumps(result, indent=2)}]

            elif tool_name == "end_codex_session":
                session_id = arguments.get("session_id")

                if not session_id:
                    raise ValueError("session_id parameter is required")

                result = await end_codex_session_impl(session_id)
                content = [{"type": "text", "text": json.dumps(result, indent=2)}]

            else:
                raise ValueError(f"Unknown tool: {tool_name}")

            return {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "result": {
                    "content": content
                }
            }

        except Exception as e:
            logger.error(f"Tool call error: {e}")
            logger.error(traceback.format_exc())

            return {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {
                    "code": -32603,
                    "message": "Internal error",
                    "data": str(e)
                }
            }

    async def handle_initialized(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle initialized notification after successful initialize."""
        logger.info("Received initialized notification - MCP handshake complete")
        # Initialized is a notification, so no response is needed
        return None

    async def handle_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Route MCP requests to appropriate handlers."""
        method = request.get("method")

        if method == "initialize":
            return await self.handle_initialize(request)
        elif method == "initialized":
            return await self.handle_initialized(request)
        elif method == "tools/list":
            return await self.handle_list_tools(request)
        elif method == "tools/call":
            return await self.handle_call_tool(request)
        else:
            logger.warning(f"Unknown method: {method}")
            return {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {
                    "code": -32601,
                    "message": "Method not found",
                    "data": method
                }
            }

    async def run(self):
        """Run the STDIO MCP server."""
        logger.info("Starting STDIO MCP Server...")
        logger.info("Ready to accept MCP connections via STDIO")

        try:
            # Read from stdin line by line
            while True:
                try:
                    line = sys.stdin.readline()
                    if not line:
                        logger.info("Received EOF from client, connection closed")
                        break

                    line = line.strip()
                    if not line:
                        logger.debug("Received empty line, skipping")
                        continue

                    logger.debug(f"Processing request: {line[:100]}...")

                    # Parse JSON-RPC request
                    try:
                        request = json.loads(line)
                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON: {e}")
                        continue

                    # Handle the request
                    response = await self.handle_request(request)

                    # Send response if there is one
                    if response:
                        response_json = json.dumps(response)
                        print(response_json)
                        sys.stdout.flush()

                except Exception as e:
                    logger.error(f"Error processing request: {e}")
                    logger.error(traceback.format_exc())

        except KeyboardInterrupt:
            logger.info("Server shutting down gracefully...")
        except Exception as e:
            logger.error(f"Server error: {e}")
            logger.error(traceback.format_exc())


async def main():
    """Main entry point for the STDIO MCP server."""
    server = StdioMCPServer()
    await server.run()


if __name__ == "__main__":
    # Always create a fresh event loop for MCP Inspector compatibility
    try:
        # Close any existing loop
        try:
            loop = asyncio.get_running_loop()
            loop.close()
        except RuntimeError:
            pass

        # Create and run with new policy on Windows
        if sys.platform == "win32":
            # Use ProactorEventLoop on Windows for better subprocess support
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

        # Run the server
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        sys.exit(1)