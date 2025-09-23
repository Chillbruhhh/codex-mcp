#!/usr/bin/env python3
"""
Minimal MCP server for debugging MCP Inspector connection.
"""

import sys
import json
import logging

# Configure logging to stderr
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def handle_request(request):
    """Handle a single MCP request."""
    method = request.get("method")
    logger.info(f"Received request: {method}")

    if method == "initialize":
        logger.info("Handling initialize")
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "minimal-debug-server",
                    "version": "1.0.0"
                }
            }
        }
    elif method == "initialized":
        logger.info("Received initialized notification")
        return None
    elif method == "tools/list":
        logger.info("Handling tools/list")
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "tools": [
                    {
                        "name": "test_tool",
                        "description": "A test tool",
                        "inputSchema": {
                            "type": "object",
                            "properties": {},
                            "required": []
                        }
                    }
                ]
            }
        }
    else:
        logger.warning(f"Unknown method: {method}")
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "error": {
                "code": -32601,
                "message": "Method not found"
            }
        }

def main():
    """Main server loop."""
    logger.info("Starting minimal MCP debug server...")
    logger.info("Ready for MCP connections")

    try:
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    logger.info("EOF received, exiting")
                    break

                line = line.strip()
                if not line:
                    continue

                logger.info(f"Received line: {line[:100]}...")

                try:
                    request = json.loads(line)
                    response = handle_request(request)

                    if response:
                        response_json = json.dumps(response)
                        print(response_json)
                        sys.stdout.flush()
                        logger.info(f"Sent response: {response_json[:100]}...")

                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON: {e}")

            except Exception as e:
                logger.error(f"Error processing request: {e}")

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt, exiting")
    except Exception as e:
        logger.error(f"Server error: {e}")

if __name__ == "__main__":
    main()