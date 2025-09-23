#!/usr/bin/env python3
"""
Debug MCP Inspector communication issues.
"""

import subprocess
import json
import time
import threading
from pathlib import Path

def read_output(process, name):
    """Read output from process in a separate thread."""
    while True:
        try:
            line = process.stdout.readline()
            if not line:
                break
            print(f"[{name} OUT] {line.strip()}")
        except:
            break

def read_errors(process, name):
    """Read stderr from process in a separate thread."""
    while True:
        try:
            line = process.stderr.readline()
            if not line:
                break
            print(f"[{name} ERR] {line.strip()}")
        except:
            break

def debug_mcp_communication():
    """Debug the exact communication pattern."""
    print("Debugging MCP Inspector communication pattern...")

    server_path = Path(__file__).parent / "stdio_server.py"
    venv_python = Path(__file__).parent / "venv" / "Scripts" / "python.exe"

    # Start server process exactly like MCP Inspector does
    process = subprocess.Popen(
        [str(venv_python), str(server_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1  # Line buffered like MCP Inspector
    )

    print(f"[+] Started server (PID: {process.pid})")

    # Start output reading threads
    stdout_thread = threading.Thread(target=read_output, args=(process, "SERVER"))
    stderr_thread = threading.Thread(target=read_errors, args=(process, "SERVER"))
    stdout_thread.daemon = True
    stderr_thread.daemon = True
    stdout_thread.start()
    stderr_thread.start()

    try:
        # Wait a moment for server to start
        time.sleep(0.5)

        # Send initialize exactly as MCP Inspector would
        print("\n[CLIENT] Sending initialize request...")
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

        request_line = json.dumps(init_request) + "\n"
        print(f"[CLIENT] Request: {request_line.strip()}")

        process.stdin.write(request_line)
        process.stdin.flush()

        # Wait for response
        time.sleep(1)

        # Send initialized notification
        print("\n[CLIENT] Sending initialized notification...")
        initialized_notification = {
            "jsonrpc": "2.0",
            "method": "initialized",
            "params": {}
        }

        notification_line = json.dumps(initialized_notification) + "\n"
        print(f"[CLIENT] Notification: {notification_line.strip()}")

        process.stdin.write(notification_line)
        process.stdin.flush()

        # Wait for processing
        time.sleep(1)

        # Try tools/list
        print("\n[CLIENT] Sending tools/list request...")
        tools_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }

        tools_line = json.dumps(tools_request) + "\n"
        print(f"[CLIENT] Request: {tools_line.strip()}")

        process.stdin.write(tools_line)
        process.stdin.flush()

        # Wait for final response
        time.sleep(2)

        print("\n[+] Communication test completed")

    except Exception as e:
        print(f"[-] Error: {e}")
    finally:
        process.terminate()
        try:
            process.wait(timeout=2)
        except:
            process.kill()

if __name__ == "__main__":
    debug_mcp_communication()