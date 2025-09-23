#!/usr/bin/env python3
"""
Test for race condition fixes in container cleanup.
Creates and ends sessions rapidly to test for race conditions.
"""

import subprocess
import json
import time
import threading
from pathlib import Path

def test_race_conditions():
    """Test race condition fixes with rapid session creation/destruction."""
    print("Testing Docker container cleanup race condition fixes...")
    print("=" * 60)

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
        response = process.stdout.readline()

        # Send initialized
        initialized = {"jsonrpc": "2.0", "method": "initialized", "params": {}}
        process.stdin.write(json.dumps(initialized) + "\n")
        process.stdin.flush()

        print("[1] Creating and ending sessions rapidly to test race conditions...")

        session_ids = []

        # Create 3 sessions rapidly
        for i in range(3):
            print(f"    Creating session {i+1}...")
            create_request = {
                "jsonrpc": "2.0",
                "id": i + 10,
                "method": "tools/call",
                "params": {
                    "name": "create_codex_session",
                    "arguments": {"agent_id": f"race_test_agent_{i}"}
                }
            }
            process.stdin.write(json.dumps(create_request) + "\n")
            process.stdin.flush()

            # Don't wait long, just get a quick response
            try:
                response = process.stdout.readline()
                response_data = json.loads(response.strip())
                if "result" in response_data:
                    content = response_data["result"]["content"][0]["text"]
                    session_data = json.loads(content)
                    if session_data.get("status") == "created":
                        session_ids.append(session_data["session_id"])
                        print(f"      Session {i+1} created: {session_data['session_id'][:20]}...")
                    else:
                        print(f"      Session {i+1} creation failed")
                else:
                    print(f"      Session {i+1} creation error: {response_data.get('error', 'Unknown')}")
            except Exception as e:
                print(f"      Session {i+1} response error: {e}")

        print(f"\n[2] Created {len(session_ids)} sessions, now ending them rapidly...")

        # End all sessions rapidly (this should trigger race conditions if they exist)
        for i, session_id in enumerate(session_ids):
            print(f"    Ending session {i+1}...")
            end_request = {
                "jsonrpc": "2.0",
                "id": i + 20,
                "method": "tools/call",
                "params": {
                    "name": "end_codex_session",
                    "arguments": {"session_id": session_id}
                }
            }
            process.stdin.write(json.dumps(end_request) + "\n")
            process.stdin.flush()

            # Quick response check
            try:
                response = process.stdout.readline()
                response_data = json.loads(response.strip())
                if "error" not in response_data:
                    print(f"      Session {i+1} ended successfully")
                else:
                    print(f"      Session {i+1} end error: {response_data['error']['message']}")
            except Exception as e:
                print(f"      Session {i+1} end response error: {e}")

        print(f"\n[3] Race condition test completed!")
        print("If no 409 Docker conflicts appeared in logs, the race condition is fixed.")

    except Exception as e:
        print(f"Test failed with exception: {e}")
    finally:
        print(f"\n[+] Stopping server...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except:
            process.kill()

if __name__ == "__main__":
    test_race_conditions()