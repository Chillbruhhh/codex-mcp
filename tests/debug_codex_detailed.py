#!/usr/bin/env python3
"""
Detailed debugging of Codex CLI execution issues.
"""

import docker
import time

def debug_codex_detailed():
    """Debug Codex CLI in detail."""
    print("Detailed Codex CLI Debugging")
    print("=" * 40)

    client = docker.from_env()

    try:
        # Test 1: Check what Codex CLI is trying to access
        print("\n[1] Testing Codex CLI with strace...")

        container = client.containers.run(
            image="codex-mcp-base:latest",
            command=["bash", "-c", "apk add --no-cache strace && strace -e trace=openat,connect,socket codex --help 2>&1 | head -20"],
            user="root",  # Need root for apk
            remove=True,
            detach=False
        )

        print(f"    Strace result: {container.decode().strip()}")

        # Test 2: Check if Codex CLI works with help
        print("\n[2] Testing Codex CLI --help...")

        container = client.containers.run(
            image="codex-mcp-base:latest",
            command=["codex", "--help"],
            user="codex",
            remove=True,
            detach=False
        )

        print(f"    Help result: {container.decode().strip()}")

        # Test 3: Test Codex CLI in interactive mode without input
        print("\n[3] Testing Codex CLI without input...")

        test_container = client.containers.create(
            image="codex-mcp-base:latest",
            command=["bash", "-c", "timeout 5 codex || echo 'Timeout or error: $?'"],
            user="codex",
            working_dir="/app/workspace",
            environment={"OPENAI_API_KEY": "sk-test"},
            auto_remove=True,
            detach=True,
            tty=True,  # Try with TTY
            stdin_open=True  # Try with stdin open
        )

        test_container.start()
        result = test_container.wait(timeout=10)
        logs = test_container.logs()

        print(f"    Exit code: {result['StatusCode']}")
        print(f"    Output: {logs.decode().strip()}")

        # Test 4: Check environment and TTY
        print("\n[4] Checking TTY and environment...")

        container = client.containers.run(
            image="codex-mcp-base:latest",
            command=["bash", "-c", "echo 'TTY:' && tty; echo 'ENV:' && env | grep -E '(TERM|TTY|DISPLAY)'; echo 'DEV:' && ls -la /dev/ | head -10"],
            user="codex",
            remove=True,
            detach=False,
            tty=True
        )

        print(f"    Environment check: {container.decode().strip()}")

        # Test 5: Try with explicit TTY allocation
        print("\n[5] Testing with proper TTY allocation...")

        test_container = client.containers.create(
            image="codex-mcp-base:latest",
            command=["bash", "-c", "echo 'hello world' | timeout 10 codex"],
            user="codex",
            working_dir="/app/workspace",
            environment={
                "OPENAI_API_KEY": "your_api_key_here",
                "TERM": "xterm"
            },
            auto_remove=True,
            detach=True,
            tty=True,
            stdin_open=True
        )

        test_container.start()
        result = test_container.wait(timeout=15)
        logs = test_container.logs()

        print(f"    TTY test exit code: {result['StatusCode']}")
        print(f"    TTY test output: {logs.decode().strip()}")

    except Exception as e:
        print(f"    FAIL Debug failed: {e}")

    print("\n" + "=" * 40)
    print("Detailed debug completed!")

if __name__ == "__main__":
    debug_codex_detailed()
