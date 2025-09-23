#!/usr/bin/env python3
"""
Direct test of Codex CLI exec mode in container.
"""

import docker
import time

def direct_codex_test():
    """Direct test of Codex CLI exec mode."""
    print("Direct Codex CLI Exec Test")
    print("=" * 30)

    client = docker.from_env()
    api_key = "your_openai_api_key_here"

    try:
        # Create a simple test container
        print("[1] Creating test container...")

        container = client.containers.create(
            image="codex-mcp-base:latest",
            command=["sleep", "300"],  # Keep alive for 5 minutes
            user="codex",
            working_dir="/app/workspace",
            environment={"OPENAI_API_KEY": api_key},
            name="direct-codex-test",
            auto_remove=True,
            detach=True
        )

        container.start()
        print(f"    Container started: {container.id[:12]}")

        # Wait a moment for container to be ready
        time.sleep(2)

        # Test 1: Simple exec command
        print("\n[2] Testing codex exec command...")

        exec_result = container.exec_run(
            cmd=["codex", "exec", "write a simple hello world function"],
            user="codex",
            workdir="/app/workspace"
        )

        print(f"    Exit code: {exec_result.exit_code}")
        if exec_result.output:
            output = exec_result.output.decode('utf-8', errors='ignore')
            print(f"    Output length: {len(output)} chars")
            print(f"    First 300 chars: {output[:300]}")
        else:
            print("    No output")

        # Test 2: Check login status
        print("\n[3] Testing login status...")

        login_result = container.exec_run(
            cmd=["codex", "login", "--check"],
            user="codex"
        )

        print(f"    Login check exit code: {login_result.exit_code}")
        if login_result.output:
            login_output = login_result.output.decode('utf-8', errors='ignore')
            print(f"    Login output: {login_output.strip()}")

        # Stop container
        container.stop()
        print("\n[4] Container stopped")

    except Exception as e:
        print(f"Test failed: {e}")

if __name__ == "__main__":
    direct_codex_test()
