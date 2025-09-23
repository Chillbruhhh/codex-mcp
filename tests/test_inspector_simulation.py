#!/usr/bin/env python3
"""
Simulate exactly what MCP Inspector does to find the issue.
"""

import subprocess
import json
import time
import threading
import sys
from pathlib import Path

def simulate_mcp_inspector():
    """Simulate the exact connection pattern MCP Inspector uses."""
    print("Simulating MCP Inspector connection pattern...")

    server_path = Path(__file__).parent / "stdio_server.py"
    venv_python = Path(__file__).parent / "venv" / "Scripts" / "python.exe"

    # Start server exactly like MCP Inspector does
    process = subprocess.Popen(
        [str(venv_python), str(server_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,  # Line buffered
        cwd=str(Path(__file__).parent)
    )

    print(f"[+] Server started (PID: {process.pid})")

    def monitor_stderr():
        """Monitor stderr for connection issues."""
        try:
            while True:
                line = process.stderr.readline()
                if not line:
                    break
                print(f"[SERVER] {line.rstrip()}")
        except:
            pass

    def monitor_stdout():
        """Monitor stdout for responses."""
        try:
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                print(f"[RESPONSE] {line.rstrip()}")
        except:
            pass

    # Start monitoring
    stderr_thread = threading.Thread(target=monitor_stderr, daemon=True)
    stdout_thread = threading.Thread(target=monitor_stdout, daemon=True)
    stderr_thread.start()
    stdout_thread.start()

    try:
        # Wait for server startup
        time.sleep(0.5)

        # Step 1: Send initialize with MCP Inspector's exact format
        print("\n[CLIENT] Sending MCP Inspector initialize...")
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "roots": {
                        "listChanged": True
                    },
                    "sampling": {}
                },
                "clientInfo": {
                    "name": "@modelcontextprotocol/inspector",
                    "version": "0.6.0"
                }
            }
        }

        request_json = json.dumps(init_request) + "\n"
        print(f"[CLIENT] Sending: {request_json.strip()}")

        process.stdin.write(request_json)
        process.stdin.flush()

        # Wait for initialize response
        time.sleep(1)

        # Step 2: Send initialized notification
        print("\n[CLIENT] Sending initialized notification...")
        initialized_notification = {
            "jsonrpc": "2.0",
            "method": "initialized",
            "params": {}
        }

        notification_json = json.dumps(initialized_notification) + "\n"
        print(f"[CLIENT] Sending: {notification_json.strip()}")

        process.stdin.write(notification_json)
        process.stdin.flush()

        # Wait for processing
        time.sleep(1)

        # Step 3: List tools like MCP Inspector does
        print("\n[CLIENT] Requesting tools list...")
        tools_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }

        tools_json = json.dumps(tools_request) + "\n"
        print(f"[CLIENT] Sending: {tools_json.strip()}")

        process.stdin.write(tools_json)
        process.stdin.flush()

        # Wait for tools response
        time.sleep(2)

        # Check server status
        if process.poll() is None:
            print("\n[+] Server is still running - connection successful!")
        else:
            print(f"\n[-] Server exited with code: {process.poll()}")

        # Keep connection alive like MCP Inspector would
        print("\n[CLIENT] Keeping connection alive...")
        time.sleep(3)

    except Exception as e:
        print(f"[-] Error during simulation: {e}")
    finally:
        if process.poll() is None:
            print("[+] Terminating server...")
            process.stdin.close()
            process.terminate()
            process.wait(timeout=5)

if __name__ == "__main__":
    simulate_mcp_inspector()