#!/usr/bin/env python3
"""
Test improved Codex CLI with timeout handling.
"""

import docker
import time

def test_improved_codex():
    """Test improved Codex CLI execution."""
    print("Testing Improved Codex CLI Execution")
    print("=" * 40)

    client = docker.from_env()
    api_key = "your_openai_api_key_here"

    try:
        # Create test container
        print("[1] Creating container...")

        container = client.containers.create(
            image="codex-mcp-base:latest",
            command=["sleep", "600"],
            user="codex",
            working_dir="/app/workspace",
            environment={"OPENAI_API_KEY": api_key},
            name="improved-codex-test",
            auto_remove=True,
            detach=True
        )

        container.start()
        print(f"    Container started: {container.id[:12]}")
        time.sleep(2)

        # Test 1: Simple request with timeout
        print("\n[2] Testing simple request with timeout...")

        message = "write a hello world function"
        timeout_seconds = 30

        exec_result = container.exec_run(
            cmd=["bash", "-c", f"timeout {timeout_seconds}s codex exec '{message}'"],
            user="codex",
            workdir="/app/workspace"
        )

        print(f"    Exit code: {exec_result.exit_code}")
        if exec_result.output:
            output = exec_result.output.decode('utf-8', errors='ignore')
            print(f"    Output length: {len(output)} chars")
            print(f"    Output preview: {output[:400]}...")
        else:
            print("    No output")

        # Test 2: Very short timeout to test timeout handling
        print("\n[3] Testing timeout handling (5 second timeout)...")

        exec_result = container.exec_run(
            cmd=["bash", "-c", "timeout 5s codex exec 'write a complex machine learning algorithm'"],
            user="codex",
            workdir="/app/workspace"
        )

        print(f"    Exit code: {exec_result.exit_code}")
        if exec_result.exit_code == 124:
            print("    Timeout handled correctly!")

        if exec_result.output:
            output = exec_result.output.decode('utf-8', errors='ignore')
            print(f"    Output: {output[:200]}...")

        # Stop container
        container.stop()
        print("\n[4] Container stopped")

    except Exception as e:
        print(f"Test failed: {e}")

if __name__ == "__main__":
    test_improved_codex()