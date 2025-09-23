#!/usr/bin/env python3
"""
Test MCP server with STDIO transport for debugging MCP Inspector connection.
"""

import sys
import json
import asyncio
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

async def main():
    """Test STDIO MCP server."""

    # Read from stdin
    print("DEBUG: Starting STDIO MCP test", file=sys.stderr)

    try:
        # Read a line from stdin
        line = sys.stdin.readline().strip()
        print(f"DEBUG: Received: {line}", file=sys.stderr)

        if line:
            try:
                request = json.loads(line)
                print(f"DEBUG: Parsed JSON: {request}", file=sys.stderr)

                # Send a simple response
                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "result": {
                        "capabilities": {
                            "tools": {},
                            "resources": {}
                        },
                        "serverInfo": {
                            "name": "codex-mcp-test",
                            "version": "0.1.0"
                        }
                    }
                }

                print(json.dumps(response))
                sys.stdout.flush()

            except json.JSONDecodeError as e:
                print(f"DEBUG: JSON decode error: {e}", file=sys.stderr)

    except Exception as e:
        print(f"DEBUG: Error: {e}", file=sys.stderr)

if __name__ == "__main__":
    asyncio.run(main())