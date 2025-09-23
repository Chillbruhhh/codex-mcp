#!/usr/bin/env python3
"""
Debug what happens when MCP Inspector actually connects.
"""

import subprocess
import json
import time
import threading
import os
from pathlib import Path

def monitor_server_process():
    """Monitor what happens when we connect like MCP Inspector does."""
    print("Monitoring server process for MCP Inspector-style connection...")

    server_path = Path(__file__).parent / "stdio_server.py"
    venv_python = Path(__file__).parent / "venv" / "Scripts" / "python.exe"

    # Add some debugging to see the exact environment
    env = os.environ.copy()

    # Start server exactly as MCP Inspector would
    print(f"Starting: {venv_python} {server_path}")

    process = subprocess.Popen(
        [str(venv_python), str(server_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=str(Path(__file__).parent)
    )

    print(f"[+] Server started (PID: {process.pid})")

    def read_stderr():
        """Read stderr continuously."""
        for line in iter(process.stderr.readline, ''):
            if line:
                print(f"[STDERR] {line.rstrip()}")

    def read_stdout():
        """Read stdout continuously."""
        for line in iter(process.stdout.readline, ''):
            if line:
                print(f"[STDOUT] {line.rstrip()}")

    # Start monitoring threads
    stderr_thread = threading.Thread(target=read_stderr, daemon=True)
    stdout_thread = threading.Thread(target=read_stdout, daemon=True)
    stderr_thread.start()
    stdout_thread.start()

    try:
        # Let it run for a moment
        time.sleep(1)

        # Check if process is still alive
        if process.poll() is None:
            print("[+] Server is running and waiting for input")

            # Send a simple message to see what happens
            print("\n[TEST] Sending initialize...")
            init_msg = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "debug", "version": "1.0"}
                }
            }

            try:
                process.stdin.write(json.dumps(init_msg) + "\n")
                process.stdin.flush()
                print("[TEST] Initialize sent")

                # Wait for response
                time.sleep(1)

                # Check if server is still running
                if process.poll() is None:
                    print("[+] Server still running after initialize")
                else:
                    print(f"[-] Server exited with code: {process.poll()}")

            except Exception as e:
                print(f"[-] Error sending initialize: {e}")
        else:
            print(f"[-] Server exited immediately with code: {process.poll()}")

    except KeyboardInterrupt:
        print("\n[+] Stopping...")
    finally:
        if process.poll() is None:
            print("[+] Terminating server...")
            process.terminate()
            process.wait(timeout=2)

if __name__ == "__main__":
    monitor_server_process()