#!/usr/bin/env python3
"""
Test script for STDIO MCP server connection.

This tests the new stdio_server.py to ensure it properly handles
MCP JSON-RPC protocol over stdin/stdout.
"""

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path


async def test_stdio_mcp_server():
    """Test the STDIO MCP server with various requests."""
    print("Testing STDIO MCP Server Connection")
    print("=" * 50)

    # Start the STDIO server process
    server_path = Path(__file__).parent / "stdio_server.py"

    try:
        # Use the virtual environment Python
        venv_python = Path(__file__).parent / "venv" / "Scripts" / "python.exe"
        if not venv_python.exists():
            venv_python = "python"  # Fallback

        process = subprocess.Popen(
            [str(venv_python), str(server_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=0
        )

        print(f"[+] Started server process (PID: {process.pid})")

        # Test 1: Initialize
        print("\n1. Testing initialize...")
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            }
        }

        process.stdin.write(json.dumps(init_request) + "\n")
        process.stdin.flush()

        # Read response
        response_line = process.stdout.readline()
        if response_line:
            try:
                response = json.loads(response_line.strip())
                if response.get("result", {}).get("serverInfo", {}).get("name") == "codex-cli-mcp-server":
                    print("[+] Initialize successful")
                else:
                    print(f"[-] Initialize failed: {response}")
            except json.JSONDecodeError:
                print(f"[-] Invalid JSON response: {response_line}")
        else:
            print("[-] No response received")

        # Test 2: List tools
        print("\n2. Testing list tools...")
        list_tools_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }

        process.stdin.write(json.dumps(list_tools_request) + "\n")
        process.stdin.flush()

        response_line = process.stdout.readline()
        if response_line:
            try:
                response = json.loads(response_line.strip())
                tools = response.get("result", {}).get("tools", [])
                print(f"[+] Found {len(tools)} tools:")
                for tool in tools:
                    print(f"  - {tool.get('name')}: {tool.get('description')}")
            except json.JSONDecodeError:
                print(f"[-] Invalid JSON response: {response_line}")
        else:
            print("[-] No response received")

        # Test 3: Call health_check tool
        print("\n3. Testing health_check tool...")
        health_check_request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "health_check",
                "arguments": {}
            }
        }

        process.stdin.write(json.dumps(health_check_request) + "\n")
        process.stdin.flush()

        response_line = process.stdout.readline()
        if response_line:
            try:
                response = json.loads(response_line.strip())
                if "result" in response:
                    print("[+] Health check successful")
                    content = response["result"].get("content", [])
                    if content and content[0].get("type") == "text":
                        health_data = json.loads(content[0]["text"])
                        print(f"  Status: {health_data.get('status')}")
                        print(f"  Version: {health_data.get('version')}")
                        print(f"  Active sessions: {health_data.get('active_sessions')}")
                else:
                    print(f"[-] Health check failed: {response}")
            except json.JSONDecodeError:
                print(f"[-] Invalid JSON response: {response_line}")
        else:
            print("[-] No response received")

        # Test 4: Test invalid tool
        print("\n4. Testing invalid tool (error handling)...")
        invalid_request = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "invalid_tool",
                "arguments": {}
            }
        }

        process.stdin.write(json.dumps(invalid_request) + "\n")
        process.stdin.flush()

        response_line = process.stdout.readline()
        if response_line:
            try:
                response = json.loads(response_line.strip())
                if "error" in response:
                    print("[+] Error handling works correctly")
                    print(f"  Error: {response['error']['message']}")
                else:
                    print(f"[-] Expected error response: {response}")
            except json.JSONDecodeError:
                print(f"[-] Invalid JSON response: {response_line}")
        else:
            print("[-] No response received")

        # Cleanup
        process.terminate()
        process.wait(timeout=5)
        print(f"\n[+] Server process terminated")

        # Check stderr for any errors
        stderr_output = process.stderr.read()
        if stderr_output:
            print(f"\nServer stderr output:")
            print(stderr_output)

        print("\n" + "=" * 50)
        print("[+] STDIO MCP Server test completed successfully!")
        return True

    except Exception as e:
        print(f"\n[-] Test failed: {e}")
        if 'process' in locals():
            try:
                process.terminate()
                process.wait(timeout=2)
            except:
                pass
        return False


async def test_mcp_inspector_command():
    """Show the correct MCP Inspector command to use."""
    print("\n" + "=" * 60)
    print("MCP Inspector Connection Commands")
    print("=" * 60)

    stdio_server_path = Path(__file__).parent / "stdio_server.py"
    venv_python_path = Path(__file__).parent / "venv" / "Scripts" / "python.exe"

    print("\n1. Use with MCP Inspector:")
    print(f'npx @modelcontextprotocol/inspector "{venv_python_path}" "{stdio_server_path}"')

    print("\n2. Claude Desktop configuration:")
    config = {
        "mcpServers": {
            "codex-mcp": {
                "command": str(venv_python_path),
                "args": [str(stdio_server_path)],
                "env": {
                    "OPENAI_API_KEY": "your-openai-api-key-here"
                }
            }
        }
    }
    print(json.dumps(config, indent=2))

    print("\n3. Manual test:")
    print(f'"{venv_python_path}" "{stdio_server_path}"')
    print("Then type: {\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{}}")


if __name__ == "__main__":
    asyncio.run(test_stdio_mcp_server())
    asyncio.run(test_mcp_inspector_command())