#!/usr/bin/env python3
"""
Basic test to check if the MCP server starts without errors.
"""

import subprocess
import json
import time
from pathlib import Path

def test_basic():
    """Basic test of server startup."""
    print("Basic MCP Server Test")
    print("=" * 30)

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

        # Check for response with simple timeout
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

        # Start reading in background
        reader_thread = threading.Thread(target=read_response)
        reader_thread.daemon = True
        reader_thread.start()

        # Wait for response with timeout
        if response_received.wait(timeout=10):
            if response_data and response_data[0]:
                print("OK Server responded to initialization")
                print(f"Response: {response_data[0][:100]}...")
                return True
            else:
                print("FAIL No response from server")
                return False
        else:
            print("FAIL Server response timed out")
            return False

    except Exception as e:
        print(f"Test failed: {e}")
        return False
    finally:
        print(f"[+] Stopping server...")
        process.terminate()
        try:
            process.wait(timeout=3)
        except:
            process.kill()

if __name__ == "__main__":
    test_basic()