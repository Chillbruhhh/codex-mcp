#!/usr/bin/env python3
"""
Test the fixed Codex CLI integration using exec mode.
"""

import subprocess
import json
import time
from pathlib import Path

def test_fixed_codex():
    """Test the fixed Codex CLI integration."""
    print("Testing Fixed Codex CLI Integration")
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

        # Create session
        print("\n[1] Creating Codex session...")
        create_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "create_codex_session",
                "arguments": {"agent_id": "fixed_test_agent"}
            }
        }
        process.stdin.write(json.dumps(create_request) + "\n")
        process.stdin.flush()

        response = json.loads(process.stdout.readline().strip())

        if "result" in response:
            content = response["result"]["content"][0]["text"]
            session_data = json.loads(content)

            if session_data.get("status") == "created":
                session_id = session_data["session_id"]
                print(f"    Session created: {session_id[:20]}...")

                # Test Codex chat
                print("\n[2] Testing Codex chat with exec mode...")
                chat_request = {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "codex_chat",
                        "arguments": {
                            "message": "Write a simple Python function that calculates the factorial of a number",
                            "session_id": session_id
                        }
                    }
                }
                process.stdin.write(json.dumps(chat_request) + "\n")
                process.stdin.flush()

                print("    Waiting for Codex response...")
                chat_response = json.loads(process.stdout.readline().strip())

                if "result" in chat_response:
                    response_content = chat_response["result"]["content"][0]["text"]
                    print(f"    SUCCESS: Got response ({len(response_content)} chars)")
                    print(f"    Preview: {response_content[:200]}...")

                    # Test code generation
                    print("\n[3] Testing code generation...")
                    code_request = {
                        "jsonrpc": "2.0",
                        "id": 4,
                        "method": "tools/call",
                        "params": {
                            "name": "codex_generate_code",
                            "arguments": {
                                "prompt": "a function that sorts a list",
                                "language": "python",
                                "session_id": session_id
                            }
                        }
                    }
                    process.stdin.write(json.dumps(code_request) + "\n")
                    process.stdin.flush()

                    code_response = json.loads(process.stdout.readline().strip())

                    if "result" in code_response:
                        code_content = code_response["result"]["content"][0]["text"]
                        print(f"    SUCCESS: Got code ({len(code_content)} chars)")
                        print(f"    Preview: {code_content[:200]}...")
                    else:
                        print(f"    FAIL: {code_response.get('error', 'Unknown error')}")

                else:
                    print(f"    FAIL: {chat_response.get('error', 'Unknown error')}")

                # End session
                print("\n[4] Ending session...")
                end_request = {
                    "jsonrpc": "2.0",
                    "id": 5,
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
                    print("    Session ended successfully")
                else:
                    print("    Session end failed")

            else:
                print(f"    FAIL: Session creation failed: {session_data}")
        else:
            print(f"    FAIL: {response.get('error', 'Unknown error')}")

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
    test_fixed_codex()