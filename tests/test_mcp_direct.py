#!/usr/bin/env python3
"""
Test the MCP server directly to see what's happening.
"""

import subprocess
import json
import time
from pathlib import Path

def test_mcp_direct():
    """Test MCP server directly."""
    print("Testing MCP Server Directly")
    print("=" * 40)

    server_path = Path(__file__).parent / "stdio_server.py"
    venv_python = Path(__file__).parent / "venv" / "Scripts" / "python.exe"

    process = subprocess.Popen(
        [str(venv_python), str(server_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=0
    )

    print(f"[+] Server started (PID: {process.pid})")

    try:
        # Initialize
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
        process.stdout.readline()

        # Send initialized
        initialized = {"jsonrpc": "2.0", "method": "initialized", "params": {}}
        process.stdin.write(json.dumps(initialized) + "\n")
        process.stdin.flush()

        # Test health check
        print("\n[1] Testing health check...")
        health_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "health_check", "arguments": {}}
        }
        process.stdin.write(json.dumps(health_request) + "\n")
        process.stdin.flush()

        response = json.loads(process.stdout.readline().strip())
        if "result" in response:
            print("    Health check successful")
        else:
            print(f"    Health check failed: {response}")

        # Test simple codex chat
        print("\n[2] Testing simple codex chat...")
        chat_request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "codex_chat",
                "arguments": {
                    "message": "hello",
                    "agent_id": "direct_test"
                }
            }
        }
        process.stdin.write(json.dumps(chat_request) + "\n")
        process.stdin.flush()

        print("    Waiting for response...")

        # Wait longer for response
        import threading
        response_received = threading.Event()
        response_data = []

        def read_response():
            try:
                resp = process.stdout.readline()
                response_data.append(resp)
                response_received.set()
            except:
                response_received.set()

        reader_thread = threading.Thread(target=read_response)
        reader_thread.daemon = True
        reader_thread.start()

        if response_received.wait(timeout=60):  # Wait up to 60 seconds
            if response_data and response_data[0]:
                response = json.loads(response_data[0].strip())
                if "result" in response:
                    content = response["result"]["content"][0]["text"]
                    print(f"    SUCCESS: {content[:200]}...")
                else:
                    print(f"    ERROR: {response}")
            else:
                print("    No response received")
        else:
            print("    TIMEOUT: No response within 60 seconds")

    except Exception as e:
        print(f"Test failed: {e}")
    finally:
        print(f"\n[+] Stopping server...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except:
            process.kill()

if __name__ == "__main__":
    test_mcp_direct()