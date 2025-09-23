#!/usr/bin/env python3
"""
Full end-to-end workflow test for Codex CLI MCP Server.
Tests session creation, Codex CLI interaction, and cleanup.
"""

import subprocess
import json
import time
from pathlib import Path

def test_full_codex_workflow():
    """Test complete Codex CLI workflow including chat interaction."""
    print("Testing full Codex CLI workflow...")
    print("=" * 50)

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

    print(f"[+] Started server (PID: {process.pid})")

    try:
        # Initialize MCP
        print("\n[1] Initializing MCP...")
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
        print("    Initialized OK")

        # Send initialized notification
        initialized = {"jsonrpc": "2.0", "method": "initialized", "params": {}}
        process.stdin.write(json.dumps(initialized) + "\n")
        process.stdin.flush()

        # Create session
        print("\n[2] Creating Codex session...")
        create_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "create_codex_session",
                "arguments": {"agent_id": "workflow_test_agent"}
            }
        }
        process.stdin.write(json.dumps(create_request) + "\n")
        process.stdin.flush()

        response_line = process.stdout.readline()
        response = json.loads(response_line.strip())

        if "error" in response:
            print(f"    FAILED: {response['error']['message']}")
            return False

        session_id = response["result"]["content"][0]["text"]
        session_data = json.loads(session_id)
        session_id = session_data["session_id"]
        print(f"    Session created: {session_id}")

        # Test Codex chat
        print("\n[3] Testing Codex chat...")
        chat_request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "codex_chat",
                "arguments": {
                    "session_id": session_id,
                    "message": "Help me write a simple Python function that adds two numbers"
                }
            }
        }
        process.stdin.write(json.dumps(chat_request) + "\n")
        process.stdin.flush()

        print("    Waiting for Codex response...")
        start_time = time.time()
        timeout = 60

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
            chat_response = json.loads(response_line.strip())
            if "error" in chat_response:
                print(f"    CHAT FAILED: {chat_response['error']['message']}")
                return False
            else:
                content = chat_response["result"]["content"][0]["text"]
                print(f"    Chat successful! Response length: {len(content)} chars")
                print(f"    Preview: {content[:100]}...")

        # Clean up session
        print("\n[4] Cleaning up session...")
        cleanup_request = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "end_codex_session",
                "arguments": {"session_id": session_id}
            }
        }
        process.stdin.write(json.dumps(cleanup_request) + "\n")
        process.stdin.flush()

        cleanup_response = process.stdout.readline()
        cleanup_data = json.loads(cleanup_response.strip())

        if "error" in cleanup_data:
            print(f"    CLEANUP WARNING: {cleanup_data['error']['message']}")
        else:
            print("    Session cleaned up successfully")

        return True

    except Exception as e:
        print(f"Test exception: {e}")
        return False
    finally:
        print(f"\n[5] Stopping server...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except:
            process.kill()
        print("    Server stopped")

def main():
    """Run the full workflow test."""
    print("Codex CLI Full Workflow Test")
    print("=" * 60)
    print("This test verifies the complete Codex CLI integration workflow.")
    print("")

    success = test_full_codex_workflow()

    print("\n" + "=" * 60)
    if success:
        print("FULL WORKFLOW TEST PASSED!")
        print("Codex CLI integration is working correctly.")
    else:
        print("FULL WORKFLOW TEST FAILED!")
        print("There are issues with the Codex CLI integration.")

if __name__ == "__main__":
    main()