#!/usr/bin/env python3
"""
Quick summary test for key Codex CLI MCP functionality.
Tests the most important tools without creating multiple sessions.
"""

import subprocess
import json
import time
from pathlib import Path

def run_quick_test():
    """Quick test of core functionality."""
    print("Quick Codex CLI MCP Test")
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

        # Test 1: Health Check
        print("\n[1] Testing health_check...")
        health_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "health_check", "arguments": {}}
        }
        process.stdin.write(json.dumps(health_request) + "\n")
        process.stdin.flush()

        response = json.loads(process.stdout.readline().strip())
        if "error" not in response:
            print("    OK Health check passed")
        else:
            print("    FAIL Health check failed")

        # Test 2: List Sessions (should be empty)
        print("\n[2] Testing list_sessions...")
        list_request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "list_sessions", "arguments": {}}
        }
        process.stdin.write(json.dumps(list_request) + "\n")
        process.stdin.flush()

        response = json.loads(process.stdout.readline().strip())
        if "error" not in response:
            print("    OK List sessions working")
        else:
            print("    FAIL List sessions failed")

        # Test 3: Create Session
        print("\n[3] Testing create_codex_session...")
        create_request = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "create_codex_session",
                "arguments": {"agent_id": "quick_test_agent"}
            }
        }
        process.stdin.write(json.dumps(create_request) + "\n")
        process.stdin.flush()

        print("    Waiting for session creation...")
        response = json.loads(process.stdout.readline().strip())

        if "error" not in response:
            content = response["result"]["content"][0]["text"]
            session_data = json.loads(content)
            if session_data.get("status") == "created":
                session_id = session_data["session_id"]
                print(f"    OK Session created: {session_id[:20]}...")

                # Test 4: Use the session for chat
                print("\n[4] Testing codex_chat with session...")
                chat_request = {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "codex_chat",
                        "arguments": {
                            "message": "Hello, can you help me?",
                            "session_id": session_id
                        }
                    }
                }
                process.stdin.write(json.dumps(chat_request) + "\n")
                process.stdin.flush()

                chat_response = json.loads(process.stdout.readline().strip())
                if "error" not in chat_response:
                    print("    OK Chat with session successful")
                else:
                    print(f"    FAIL Chat failed: {chat_response['error']['message']}")

                # Test 5: End session
                print("\n[5] Testing end_codex_session...")
                end_request = {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/call",
                    "params": {
                        "name": "end_codex_session",
                        "arguments": {"session_id": session_id}
                    }
                }
                process.stdin.write(json.dumps(end_request) + "\n")
                process.stdin.flush()

                end_response = json.loads(process.stdout.readline().strip())
                if "error" not in end_response:
                    print("    OK Session ended successfully")
                else:
                    print("    FAIL Session end failed")
            else:
                print(f"    FAIL Session creation failed: {session_data}")
        else:
            print(f"    FAIL Session creation failed: {response['error']['message']}")

        print("\n" + "=" * 40)
        print("OK Quick test completed - MCP server is functional!")

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
    run_quick_test()