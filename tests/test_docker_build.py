#!/usr/bin/env python3
"""
Test Docker container building for Codex CLI.
"""

import docker
import tempfile
from pathlib import Path

def test_dockerfile_build():
    """Test if our Dockerfile template builds successfully."""
    print("Testing Codex CLI Docker image build...")

    # The corrected Dockerfile content from container_manager.py
    dockerfile_content = """FROM node:20-alpine

# Install system dependencies
RUN apk add --no-cache \\
    git \\
    curl \\
    python3 \\
    py3-pip \\
    bash

# Install Codex CLI globally
RUN npm install -g @openai/codex

# Create non-root user for security (Alpine Linux syntax)
RUN addgroup -g 1000 codex && \\
    adduser -D -u 1000 -G codex codex

# Create directories
RUN mkdir -p /app/workspace /app/config /app/sessions && \\
    chown -R codex:codex /app

# Switch to non-root user
USER codex
WORKDIR /app

# Set up PATH to include Codex CLI
ENV PATH="/usr/local/bin:$PATH"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
    CMD codex --version || exit 1

# Default command
CMD ["bash", "-c", "echo 'Codex CLI container ready' && sleep infinity"]
"""

    try:
        client = docker.from_env()
        print("[+] Docker client connected")

        # Create temporary directory for build context
        with tempfile.TemporaryDirectory() as temp_dir:
            dockerfile_path = Path(temp_dir) / "Dockerfile"
            dockerfile_path.write_text(dockerfile_content)

            print(f"[+] Created Dockerfile in {temp_dir}")
            print(f"[+] Dockerfile content length: {len(dockerfile_content)} chars")

            # Test build
            print("[+] Starting Docker build...")
            try:
                image, build_logs = client.images.build(
                    path=temp_dir,
                    tag="codex-cli-base:test",
                    rm=True,
                    nocache=True  # Force fresh build to test changes
                )

                print(f"[+] Build successful! Image ID: {image.id[:12]}")

                # Show last few build log lines
                log_lines = []
                for chunk in build_logs:
                    if 'stream' in chunk:
                        log_lines.append(chunk['stream'].strip())

                print("[+] Last few build steps:")
                for line in log_lines[-5:]:
                    if line:
                        print(f"    {line}")

                return True

            except Exception as build_error:
                print(f"[-] Build failed: {build_error}")
                return False

    except Exception as e:
        print(f"[-] Docker setup failed: {e}")
        return False

if __name__ == "__main__":
    success = test_dockerfile_build()
    if success:
        print("\n[+] Docker build test PASSED!")
    else:
        print("\n[-] Docker build test FAILED!")