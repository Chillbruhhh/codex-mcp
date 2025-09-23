#!/usr/bin/env python3
"""
Comprehensive test of all 7 MCP tools.
"""

import subprocess
import json
import time
from pathlib import Path

def test_all_mcp_tools():
    """Test every single MCP tool to ensure they all work."""
    print("Testing ALL 7 MCP Tools")
    print("=" * 50)

    server_path = Path(__file__).parent / "stdio_server.py"
    venv_python = Path(__file__).parent / "venv" / "Scripts" / "python.exe"

    # Start server process
    process = subprocess.Popen(
        [str(venv_python), str(server_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=0
    )

    print(f"[+] Server started (PID: {process.pid})")

    def send_request(request, test_name):
        """Send a request and get response."""
        print(f"\n{test_name}")
        print("-" * len(test_name))

        request_json = json.dumps(request) + "\n"
        process.stdin.write(request_json)
        process.stdin.flush()

        response_line = process.stdout.readline()
        if response_line:
            try:
                response = json.loads(response_line.strip())
                if "error" in response:
                    print(f"[-] ERROR: {response['error']['message']}")
                    return False
                else:
                    print("[+] SUCCESS")
                    return True
            except json.JSONDecodeError:
                print(f"[-] INVALID JSON: {response_line}")
                return False
        else:
            print("[-] NO RESPONSE")
            return False

    try:
        # Initialize handshake first
        print("Initializing MCP handshake...")

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
        send_request(init_request, "Initialize")

        initialized_notification = {
            "jsonrpc": "2.0",
            "method": "initialized",
            "params": {}
        }
        process.stdin.write(json.dumps(initialized_notification) + "\n")
        process.stdin.flush()

        print("\n" + "=" * 50)
        print("TESTING ALL TOOLS")
        print("=" * 50)

        test_results = {}

        # Test 1: health_check
        test_results["health_check"] = send_request({
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {
                "name": "health_check",
                "arguments": {}
            }
        }, "Tool 1: health_check")

        # Test 2: get_auth_status
        test_results["get_auth_status"] = send_request({
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {
                "name": "get_auth_status",
                "arguments": {}
            }
        }, "Tool 2: get_auth_status")

        # Test 3: list_sessions
        test_results["list_sessions"] = send_request({
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {
                "name": "list_sessions",
                "arguments": {}
            }
        }, "Tool 3: list_sessions")

        # Test 4: list_sessions with agent_id filter
        test_results["list_sessions_filtered"] = send_request({
            "jsonrpc": "2.0",
            "id": 13,
            "method": "tools/call",
            "params": {
                "name": "list_sessions",
                "arguments": {
                    "agent_id": "test_agent"
                }
            }
        }, "Tool 3b: list_sessions (with agent filter)")

        # Test 5: create_codex_session
        test_results["create_codex_session"] = send_request({
            "jsonrpc": "2.0",
            "id": 14,
            "method": "tools/call",
            "params": {
                "name": "create_codex_session",
                "arguments": {
                    "agent_id": "test_agent_123"
                }
            }
        }, "Tool 4: create_codex_session")

        # Test 6: codex_chat (should fail without session)
        test_results["codex_chat"] = send_request({
            "jsonrpc": "2.0",
            "id": 15,
            "method": "tools/call",
            "params": {
                "name": "codex_chat",
                "arguments": {
                    "message": "Hello, can you help me with Python?",
                    "agent_id": "test_agent_456"
                }
            }
        }, "Tool 5: codex_chat")

        # Test 7: codex_generate_code
        test_results["codex_generate_code"] = send_request({
            "jsonrpc": "2.0",
            "id": 16,
            "method": "tools/call",
            "params": {
                "name": "codex_generate_code",
                "arguments": {
                    "prompt": "Create a simple hello world function",
                    "language": "python",
                    "agent_id": "test_agent_789"
                }
            }
        }, "Tool 6: codex_generate_code")

        # Test 8: end_codex_session (should fail - no session to end)
        test_results["end_codex_session"] = send_request({
            "jsonrpc": "2.0",
            "id": 17,
            "method": "tools/call",
            "params": {
                "name": "end_codex_session",
                "arguments": {
                    "session_id": "fake_session_id"
                }
            }
        }, "Tool 7: end_codex_session")

        # Summary
        print("\n" + "=" * 50)
        print("TEST RESULTS SUMMARY")
        print("=" * 50)

        working_tools = sum(1 for success in test_results.values() if success)
        total_tools = len(test_results)

        for tool_name, success in test_results.items():
            status = "[+] WORKING" if success else "[-] BROKEN"
            print(f"{tool_name:25} {status}")

        print(f"\nWorking Tools: {working_tools}/{total_tools}")

        if working_tools == total_tools:
            print("[+] ALL TOOLS ARE WORKING!")
        else:
            print(f"[-] {total_tools - working_tools} tools need attention")

    except Exception as e:
        print(f"[-] Test failed: {e}")
    finally:
        process.terminate()
        process.wait(timeout=5)

        # Check stderr for any errors
        stderr_output = process.stderr.read()
        if stderr_output:
            print(f"\nServer stderr (last 500 chars):")
            print(stderr_output[-500:])

if __name__ == "__main__":
    test_all_mcp_tools()