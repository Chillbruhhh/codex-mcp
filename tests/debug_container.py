#!/usr/bin/env python3
"""
Debug container creation and execution issues.
"""

import docker
import time
import tempfile
from pathlib import Path

def debug_container():
    """Debug container creation and check what's going wrong."""
    print("Debug: Container Creation and Execution")
    print("=" * 50)

    client = docker.from_env()

    # Step 1: Check if base image exists
    print("[1] Checking if base image exists...")
    try:
        image = client.images.get("codex-mcp-base:latest")
        print(f"    OK Base image exists: {image.id[:12]}")
    except docker.errors.ImageNotFound:
        print("    FAIL Base image not found")
        print("    Building base image...")

        # Create Dockerfile
        dockerfile_content = """
FROM node:20-alpine

# Install system dependencies
RUN apk add --no-cache \\
    git \\
    curl \\
    python3 \\
    py3-pip \\
    bash

# Install Codex CLI globally
RUN npm install -g @openai/codex

# Create non-root user (Alpine Linux syntax)
RUN addgroup -g 1001 codex && \\
    adduser -D -u 1001 -G codex codex

# Create directories
RUN mkdir -p /app/workspace /app/config /app/sessions && \\
    chown -R codex:codex /app

# Switch to non-root user
USER codex
WORKDIR /app

# Set up PATH
ENV PATH="/usr/local/bin:$PATH"

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
    CMD codex --version || exit 1
"""

        with tempfile.TemporaryDirectory() as temp_dir:
            dockerfile_path = Path(temp_dir) / "Dockerfile"
            dockerfile_path.write_text(dockerfile_content)

            print("    Building image (this may take a few minutes)...")
            image, build_logs = client.images.build(
                path=temp_dir,
                tag="codex-mcp-base:latest",
                rm=True
            )
            print(f"    OK Image built: {image.id[:12]}")

    # Step 2: Test basic container creation
    print("\n[2] Testing basic container creation...")

    try:
        container = client.containers.create(
            image="codex-mcp-base:latest",
            command=["sleep", "30"],  # Simple command to keep container alive
            name="debug-codex-test",
            user="codex",
            working_dir="/app/workspace",
            auto_remove=True,
            detach=True
        )

        print(f"    OK Container created: {container.id[:12]}")

        # Start the container
        container.start()
        print("    OK Container started")

        # Wait a moment and check status
        time.sleep(2)
        container.reload()
        print(f"    Status: {container.status}")

        if container.status == "running":
            print("    OK Container is running successfully")

            # Test basic commands
            print("\n[3] Testing basic commands in container...")

            # Test whoami
            result = container.exec_run("whoami", user="codex")
            print(f"    whoami: {result.output.decode().strip()} (exit code: {result.exit_code})")

            # Test which codex
            result = container.exec_run("which codex", user="codex")
            print(f"    which codex: {result.output.decode().strip()} (exit code: {result.exit_code})")

            # Test codex version
            result = container.exec_run("codex --version", user="codex", environment={"OPENAI_API_KEY": "test"})
            print(f"    codex --version: {result.output.decode().strip()} (exit code: {result.exit_code})")

            # Test node version
            result = container.exec_run("node --version", user="codex")
            print(f"    node --version: {result.output.decode().strip()} (exit code: {result.exit_code})")

            # Test npm list global
            result = container.exec_run("npm list -g --depth=0", user="codex")
            print(f"    npm global packages: {result.output.decode().strip()[:200]}...")

        else:
            print(f"    FAIL Container failed to start properly: {container.status}")

            # Get logs
            logs = container.logs()
            print(f"    Logs: {logs.decode()}")

        # Stop container
        container.stop()
        print("    OK Container stopped")

    except Exception as e:
        print(f"    FAIL Container test failed: {e}")

    # Step 3: Test the exact command we're trying to run
    print("\n[4] Testing exact Codex CLI execution...")

    try:
        container = client.containers.create(
            image="codex-mcp-base:latest",
            command=["bash", "-c", "echo 'test' | codex"],
            name="debug-codex-exec",
            user="codex",
            working_dir="/app/workspace",
            environment={"OPENAI_API_KEY": "sk-test"},
            auto_remove=True,
            detach=True
        )

        container.start()
        print("    OK Test execution container started")

        # Wait for it to finish
        result = container.wait(timeout=30)
        print(f"    Exit code: {result['StatusCode']}")

        # Get logs
        logs = container.logs()
        print(f"    Output: {logs.decode()}")

    except Exception as e:
        print(f"    FAIL Execution test failed: {e}")

    print("\n" + "=" * 50)
    print("Debug completed!")

if __name__ == "__main__":
    debug_container()