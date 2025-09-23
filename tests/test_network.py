#!/usr/bin/env python3
"""
Test network connectivity and Codex CLI with real API key.
"""

import docker
import os
import time

def test_network_and_codex():
    """Test network connectivity and Codex CLI execution."""
    print("Testing Network Connectivity and Codex CLI")
    print("=" * 50)

    client = docker.from_env()

    # Get the real API key from environment
    api_key = os.environ.get('OPENAI_API_KEY', 'sk-test')

    print(f"Using API key: {api_key[:8]}..." if api_key.startswith('sk-') else "No valid API key")

    try:
        # Test 1: Network connectivity
        print("\n[1] Testing basic network connectivity...")

        container = client.containers.run(
            image="codex-mcp-base:latest",
            command=["ping", "-c", "3", "8.8.8.8"],
            user="codex",
            remove=True,
            detach=False
        )

        print(f"    Ping result: {container.decode().strip()}")

        # Test 2: DNS resolution
        print("\n[2] Testing DNS resolution...")

        container = client.containers.run(
            image="codex-mcp-base:latest",
            command=["nslookup", "api.openai.com"],
            user="codex",
            remove=True,
            detach=False
        )

        print(f"    DNS result: {container.decode().strip()}")

        # Test 3: HTTPS connectivity to OpenAI
        print("\n[3] Testing HTTPS connectivity to OpenAI...")

        container = client.containers.run(
            image="codex-mcp-base:latest",
            command=["curl", "-I", "https://api.openai.com/v1/models"],
            user="codex",
            remove=True,
            detach=False
        )

        print(f"    HTTPS result: {container.decode().strip()}")

        # Test 4: Codex CLI with real API key
        print("\n[4] Testing Codex CLI with real API key...")

        container = client.containers.run(
            image="codex-mcp-base:latest",
            command=["bash", "-c", "echo 'hello' | codex"],
            user="codex",
            working_dir="/app/workspace",
            environment={"OPENAI_API_KEY": api_key},
            remove=True,
            detach=False,
            network_mode="bridge"  # Explicitly set network mode
        )

        print(f"    Codex result: {container.decode().strip()}")

        # Test 5: Interactive Codex test with timeout
        print("\n[5] Testing Codex CLI with timeout...")

        test_container = client.containers.create(
            image="codex-mcp-base:latest",
            command=["bash", "-c", "timeout 10 bash -c 'echo \"write a hello world function\" | codex'"],
            user="codex",
            working_dir="/app/workspace",
            environment={"OPENAI_API_KEY": api_key},
            auto_remove=True,
            detach=True,
            network_mode="bridge"
        )

        test_container.start()
        result = test_container.wait(timeout=15)
        logs = test_container.logs()

        print(f"    Exit code: {result['StatusCode']}")
        print(f"    Output: {logs.decode().strip()}")

    except Exception as e:
        print(f"    FAIL Test failed: {e}")

    print("\n" + "=" * 50)
    print("Network test completed!")

if __name__ == "__main__":
    test_network_and_codex()