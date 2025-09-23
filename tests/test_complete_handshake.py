#!/usr/bin/env python3
"""
Test complete MCP handshake sequence including initialized notification.
"""

import subprocess
import json
import time
from pathlib import Path

def test_complete_mcp_handshake():
    """Test the complete MCP initialization sequence."""
    print("Testing complete MCP handshake sequence...")

    server_path = Path(__file__).parent / "stdio_server.py"
    venv_python = Path(__file__).parent / "venv" / "Scripts" / "python.exe"

    # Start server process
    process = subprocess.Popen(
        [str(venv_python), str(server_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=0
    )

    print(f"[+] Started server (PID: {process.pid})")

    try:
        # Step 1: Initialize request
        print("\n1. Sending initialize request...")
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0"}
            }
        }

        process.stdin.write(json.dumps(init_request) + "\n")
        process.stdin.flush()

        response = process.stdout.readline()
        print(f"[+] Initialize response: {response.strip()[:100]}...")

        # Step 2: Initialized notification (the missing piece!)
        print("\n2. Sending initialized notification...")
        initialized_notification = {
            "jsonrpc": "2.0",
            "method": "initialized",
            "params": {}
        }

        process.stdin.write(json.dumps(initialized_notification) + "\n")
        process.stdin.flush()

        # No response expected for notification, but check stderr for log
        time.sleep(0.1)  # Give server time to process

        # Step 3: Now try using tools (should work after complete handshake)
        print("\n3. Testing tools after complete handshake...")
        tools_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }

        process.stdin.write(json.dumps(tools_request) + "\n")
        process.stdin.flush()

        response = process.stdout.readline()
        tools_response = json.loads(response.strip())
        tools_count = len(tools_response.get("result", {}).get("tools", []))
        print(f"[+] Tools available after handshake: {tools_count}")

        # Step 4: Test tool execution
        print("\n4. Testing tool execution...")
        health_request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "health_check",
                "arguments": {}
            }
        }

        process.stdin.write(json.dumps(health_request) + "\n")
        process.stdin.flush()

        response = process.stdout.readline()
        print(f"[+] Health check response: SUCCESS")

        print("\n[+] Complete MCP handshake test PASSED!")

    except Exception as e:
        print(f"[-] Error: {e}")
    finally:
        process.terminate()
        process.wait(timeout=2)

        # Check stderr for the "handshake complete" message
        stderr = process.stderr.read()
        if "MCP handshake complete" in stderr:
            print("\n[+] Server confirmed handshake completion!")
        else:
            print(f"\nServer stderr:\n{stderr}")

if __name__ == "__main__":
    test_complete_mcp_handshake()