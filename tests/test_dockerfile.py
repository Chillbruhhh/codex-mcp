#!/usr/bin/env python3
"""
Test script to build the base image and verify the logging script is created.
"""

import asyncio
import tempfile
import docker
from pathlib import Path

# Import the container manager
import sys
sys.path.insert(0, 'src')
from src.container_manager import CodexContainerManager
from src.utils.config import load_config

async def test_base_image_build():
    """Test building the base image and verify script creation."""

    # Load config and create manager
    config = load_config()
    manager = CodexContainerManager(config)

    # Get the dockerfile content
    dockerfile_content = manager._generate_dockerfile()
    print("Generated Dockerfile content:")
    print("=" * 60)
    print(dockerfile_content)
    print("=" * 60)

    # Create temporary directory for build context
    with tempfile.TemporaryDirectory() as temp_dir:
        dockerfile_path = Path(temp_dir) / "Dockerfile"
        dockerfile_path.write_text(dockerfile_content)

        print(f"Building image in {temp_dir}")

        # Build the image using Docker client
        client = docker.from_env()
        try:
            image, build_logs = client.images.build(
                path=temp_dir,
                tag="test-codex-base:latest",
                rm=True,
                forcerm=True
            )

            print("Build completed successfully!")
            print("Build logs:")
            for log in build_logs:
                if 'stream' in log:
                    print(log['stream'].strip())

            # Test the script in the built image
            print("\nTesting script existence in built image...")
            container = client.containers.run(
                image.id,
                command=["ls", "-la", "/app/logging_startup.sh"],
                remove=True,
                detach=False
            )
            print(f"Script check result: {container}")

            # Test script execution
            print("\nTesting script execution...")
            container = client.containers.run(
                image.id,
                command=["head", "-20", "/app/logging_startup.sh"],
                remove=True,
                detach=False
            )
            print(f"Script content (first 20 lines):\n{container}")

        except Exception as e:
            print(f"Build failed: {e}")
            if hasattr(e, 'build_log'):
                for log in e.build_log:
                    if 'stream' in log:
                        print(log['stream'].strip())

if __name__ == "__main__":
    asyncio.run(test_base_image_build())