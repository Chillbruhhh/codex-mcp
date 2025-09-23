#!/usr/bin/env python3
"""
Final test of Codex CLI with git repo check fix.
"""

import docker
import time

def test_final_codex():
    """Final test with git repo check fix."""
    print("Final Codex CLI Test")
    print("=" * 30)

    client = docker.from_env()
    api_key = "your_openai_api_key_here"

    try:
        # Create test container
        print("[1] Creating container...")

        container = client.containers.create(
            image="codex-mcp-base:latest",
            command=["sleep", "300"],
            user="codex",
            working_dir="/app/workspace",
            environment={"OPENAI_API_KEY": api_key},
            name="final-codex-test",
            auto_remove=True,
            detach=True
        )

        container.start()
        print(f"    Container started: {container.id[:12]}")
        time.sleep(2)

        # Test: Codex CLI exec with skip git repo check
        print("\n[2] Testing Codex CLI with --skip-git-repo-check...")

        message = "write a simple hello world function in Python"
        timeout_seconds = 60

        exec_result = container.exec_run(
            cmd=["bash", "-c", f"timeout {timeout_seconds}s codex exec --skip-git-repo-check '{message}'"],
            user="codex",
            workdir="/app/workspace"
        )

        print(f"    Exit code: {exec_result.exit_code}")

        if exec_result.output:
            output = exec_result.output.decode('utf-8', errors='ignore')
            print(f"    Output length: {len(output)} chars")

            # Look for actual code in the output
            if "def " in output or "function" in output or "print" in output:
                print("    SUCCESS: Found code in output!")
                print(f"    Full output:\n{output}")
            else:
                print(f"    Output preview: {output[:500]}...")
        else:
            print("    No output")

        # Stop container
        container.stop()
        print("\n[3] Container stopped")

    except Exception as e:
        print(f"Test failed: {e}")

if __name__ == "__main__":
    test_final_codex()
