#!/usr/bin/env python3
"""
Test Codex CLI exec mode vs interactive mode.
"""

import docker
import time

def test_codex_exec():
    """Test different Codex CLI execution modes."""
    print("Testing Codex CLI Execution Modes")
    print("=" * 40)

    client = docker.from_env()
    api_key = "your_openai_api_key_here"

    try:
        # Test 1: Use exec mode (non-interactive)
        print("\n[1] Testing Codex CLI exec mode...")

        test_container = client.containers.create(
            image="codex-mcp-base:latest",
            command=["codex", "exec", "write a hello world function in python"],
            user="codex",
            working_dir="/app/workspace",
            environment={"OPENAI_API_KEY": api_key},
            auto_remove=True,
            detach=True
        )

        test_container.start()
        result = test_container.wait(timeout=30)
        logs = test_container.logs()

        print(f"    Exec mode exit code: {result['StatusCode']}")
        print(f"    Exec mode output: {logs.decode('utf-8', errors='ignore').strip()}")

        # Test 2: Test login status
        print("\n[2] Testing Codex CLI login status...")

        test_container = client.containers.create(
            image="codex-mcp-base:latest",
            command=["codex", "login", "--check"],
            user="codex",
            working_dir="/app/workspace",
            environment={"OPENAI_API_KEY": api_key},
            auto_remove=True,
            detach=True
        )

        test_container.start()
        result = test_container.wait(timeout=10)
        logs = test_container.logs()

        print(f"    Login check exit code: {result['StatusCode']}")
        print(f"    Login check output: {logs.decode('utf-8', errors='ignore').strip()}")

        # Test 3: Try with proto mode (protocol stream)
        print("\n[3] Testing Codex CLI proto mode...")

        test_container = client.containers.create(
            image="codex-mcp-base:latest",
            command=["bash", "-c", "echo 'write hello world' | timeout 15 codex proto"],
            user="codex",
            working_dir="/app/workspace",
            environment={"OPENAI_API_KEY": api_key},
            auto_remove=True,
            detach=True
        )

        test_container.start()
        result = test_container.wait(timeout=20)
        logs = test_container.logs()

        print(f"    Proto mode exit code: {result['StatusCode']}")
        print(f"    Proto mode output: {logs.decode('utf-8', errors='ignore').strip()}")

        # Test 4: Test with explicit non-interactive
        print("\n[4] Testing with no TTY (non-interactive)...")

        test_container = client.containers.create(
            image="codex-mcp-base:latest",
            command=["bash", "-c", "echo 'write hello world' | codex"],
            user="codex",
            working_dir="/app/workspace",
            environment={
                "OPENAI_API_KEY": api_key,
                "CI": "true",  # Indicate non-interactive environment
                "TERM": "dumb"
            },
            auto_remove=True,
            detach=True,
            tty=False,  # Explicitly no TTY
            stdin_open=False
        )

        test_container.start()
        result = test_container.wait(timeout=15)
        logs = test_container.logs()

        print(f"    Non-TTY exit code: {result['StatusCode']}")
        print(f"    Non-TTY output: {logs.decode('utf-8', errors='ignore').strip()}")

    except Exception as e:
        print(f"    FAIL Test failed: {e}")

    print("\n" + "=" * 40)
    print("Execution mode test completed!")

if __name__ == "__main__":
    test_codex_exec()
