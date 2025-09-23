#!/usr/bin/env python3
"""
Simple test of MCP tools to identify which ones work.
"""

import subprocess
import json
import time
from pathlib import Path

def test_single_tool(tool_name, arguments=None):
    """Test a single tool."""
    if arguments is None:
        arguments = {}

    print(f"\nTesting: {tool_name}")
    print("-" * 40)

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

        # Read init response
        init_response = process.stdout.readline()

        # Send initialized
        initialized = {"jsonrpc": "2.0", "method": "initialized", "params": {}}
        process.stdin.write(json.dumps(initialized) + "\n")
        process.stdin.flush()

        # Test the tool
        tool_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        process.stdin.write(json.dumps(tool_request) + "\n")
        process.stdin.flush()

        # Read response with timeout
        response_line = process.stdout.readline()

        if response_line:
            try:
                response = json.loads(response_line.strip())
                if "error" in response:
                    print(f"ERROR: {response['error']['message']}")
                    return False
                elif "result" in response:
                    print("SUCCESS")
                    content = response["result"].get("content", [])
                    if content:
                        print(f"Response length: {len(str(content))}")
                    return True
                else:
                    print("UNKNOWN RESPONSE FORMAT")
                    return False
            except json.JSONDecodeError as e:
                print(f"INVALID JSON: {e}")
                return False
        else:
            print("NO RESPONSE")
            return False

    except Exception as e:
        print(f"EXCEPTION: {e}")
        return False
    finally:
        process.terminate()
        try:
            process.wait(timeout=2)
        except:
            process.kill()

def main():
    """Test all tools one by one."""
    print("Testing MCP Tools One by One")
    print("=" * 50)

    # Test each tool individually
    tools_to_test = [
        ("health_check", {}),
        ("get_auth_status", {}),
        ("list_sessions", {}),
        ("list_sessions", {"agent_id": "test"}),
        ("create_codex_session", {"agent_id": "test_agent"}),
        ("codex_chat", {"message": "Hello", "agent_id": "test"}),
        ("codex_generate_code", {"prompt": "print hello", "agent_id": "test"}),
        ("end_codex_session", {"session_id": "fake"})
    ]

    results = {}
    for tool_name, args in tools_to_test:
        key = f"{tool_name}_{len(args)}"
        results[key] = test_single_tool(tool_name, args)
        time.sleep(0.5)  # Brief pause between tests

    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    for key, success in results.items():
        status = "[+]" if success else "[-]"
        print(f"{status} {key}")

if __name__ == "__main__":
    main()