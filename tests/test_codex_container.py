#!/usr/bin/env python3
"""
Test Codex CLI container creation with the fixed Docker configuration.
"""

import subprocess
import json
import time
from pathlib import Path

def test_codex_container_creation():
    """Test if Codex container creation works now."""
    print("Testing Codex CLI container creation...")
    print("=" * 50)

    server_path = Path(__file__).parent / "stdio_server.py"
    venv_python = Path(__file__).parent / "venv" / "Scripts" / "python.exe"

    # Start fresh server process to pick up the code changes
    process = subprocess.Popen(
        [str(venv_python), str(server_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=0
    )

    print(f"[+] Started fresh server (PID: {process.pid})")

    try:
        # Initialize MCP handshake
        print("\n[1] Initializing MCP handshake...")

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

        # Read init response
        init_response = process.stdout.readline()
        print("    Initialized OK")

        # Send initialized notification
        initialized = {"jsonrpc": "2.0", "method": "initialized", "params": {}}
        process.stdin.write(json.dumps(initialized) + "\n")
        process.stdin.flush()

        # Test container creation
        print("\n[2] Testing create_codex_session...")

        create_session_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "create_codex_session",
                "arguments": {
                    "agent_id": "test_container_agent"
                }
            }
        }

        process.stdin.write(json.dumps(create_session_request) + "\n")
        process.stdin.flush()

        print("    Waiting for container creation (this may take 30-60 seconds)...")

        # Wait for response with timeout
        start_time = time.time()
        timeout = 120  # 2 minutes for container build

        response_line = None
        while time.time() - start_time < timeout:
            try:
                response_line = process.stdout.readline()
                if response_line:
                    break
                time.sleep(0.1)
            except:
                break

        if response_line:
            try:
                response = json.loads(response_line.strip())

                if "error" in response:
                    print(f"    FAILED: {response['error']['message']}")
                    return False
                elif "result" in response:
                    print("    SUCCESS: Container created!")

                    # Show response details
                    content = response["result"].get("content", [])
                    if content and content[0].get("type") == "text":
                        result_text = content[0]["text"]
                        print(f"    Response: {result_text[:200]}...")

                    return True
                else:
                    print(f"    UNKNOWN RESPONSE: {response}")
                    return False

            except json.JSONDecodeError as e:
                print(f"    INVALID JSON: {e}")
                print(f"    Raw response: {response_line}")
                return False
        else:
            print("    TIMEOUT: No response within 2 minutes")
            return False

    except Exception as e:
        print(f"Test exception: {e}")
        return False
    finally:
        print(f"\n[3] Cleaning up...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except:
            process.kill()
        print("    Server stopped")

def main():
    """Run the container creation test."""
    print("Codex CLI Container Creation Test")
    print("=" * 60)
    print("This test checks if the Docker container building fix worked.")
    print("It will attempt to create a Codex CLI session container.")
    print("")

    success = test_codex_container_creation()

    print("\n" + "=" * 60)
    if success:
        print("CONTAINER CREATION TEST PASSED!")
        print("The Docker container fix is working correctly.")
    else:
        print("CONTAINER CREATION TEST FAILED!")
        print("There may still be Docker configuration issues.")

if __name__ == "__main__":
    main()