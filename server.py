#!/usr/bin/env python3
"""
Main entry point for the Codex CLI MCP Server.

This script starts the FastMCP server with all configured tools and handles
the lifecycle of the MCP server process.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.mcp_server import create_mcp_server


def main():
    """Main entry point for the Codex CLI MCP Server."""
    # Only log to stderr to avoid interfering with STDIO MCP protocol
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    server = create_mcp_server()

    logging.info("Starting Codex CLI MCP Server...")
    logging.info(f"Server version: 0.1.0")
    logging.info("Ready to accept MCP connections via STDIO")

    try:
        # FastMCP uses uvicorn internally, so we need to configure it properly
        import uvicorn
        import os

        # Check if we're running in container mode (with port) or stdio mode
        if os.getenv("CONTAINER_MODE", "false").lower() == "true":
            # Container mode - run HTTP server on port 8210
            logging.info("Starting in container mode on port 8210")

            # Try the legacy SSE transport for Cline compatibility
            try:
                # Try legacy SSE transport first
                logging.info("Attempting legacy SSE transport for Cline compatibility")
                server.run(transport="sse", host="0.0.0.0", port=8210)
            except Exception as e:
                logging.error(f"SSE transport failed: {e}")
                # Fallback to default HTTP transport
                logging.info("Falling back to Streamable HTTP transport")
                uvicorn.run(server.http_app(), host="0.0.0.0", port=8210)
        else:
            # STDIO mode - standard MCP protocol
            logging.info("Starting in STDIO mode")
            server.run()
    except KeyboardInterrupt:
        logging.info("Server shutting down gracefully...")
    except Exception as e:
        logging.error(f"Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()