#!/usr/bin/env python3
"""
Test persistent connection to STDIO MCP server.
"""

import subprocess
import json
import time
from pathlib import Path

def test_persistent_connection():
    """Test multiple requests to the same server instance."""
    print("Testing persistent STDIO MCP server connection...")

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
        # Test 1: Initialize
        print("\n1. Testing initialize...")
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"}
            }
        }

        process.stdin.write(json.dumps(init_request) + "\n")
        process.stdin.flush()

        response = process.stdout.readline()
        print(f"Response: {response.strip()}")

        # Test 2: List tools (same connection)
        print("\n2. Testing list tools on same connection...")
        list_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }

        process.stdin.write(json.dumps(list_request) + "\n")
        process.stdin.flush()

        response = process.stdout.readline()
        print(f"Response: {response.strip()}")

        # Test 3: Health check (same connection)
        print("\n3. Testing health check on same connection...")
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
        print(f"Response: {response.strip()}")

        print("\n[+] Persistent connection test completed!")

    except Exception as e:
        print(f"[-] Error: {e}")
    finally:
        process.terminate()
        process.wait(timeout=2)

        # Check stderr
        stderr = process.stderr.read()
        if stderr:
            print(f"\nServer stderr:\n{stderr}")

if __name__ == "__main__":
    test_persistent_connection()