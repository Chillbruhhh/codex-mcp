#!/usr/bin/env python3
"""
Manual Docker container builder for Codex CLI.
"""

import sys
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.container_manager import CodexContainerManager
from src.utils.config import get_config

async def build_codex_container():
    """Build the Codex CLI Docker container manually."""
    print("Building Codex CLI Docker Container")
    print("=" * 50)

    try:
        # Initialize container manager
        config = get_config()
        container_manager = CodexContainerManager(config)

        print("[1] Checking if container exists...")

        # Try to get existing image
        try:
            image = container_manager.docker_client.images.get("codex-mcp-base:latest")
            print(f"    ✅ Image already exists: {image.id[:12]}")

            # Ask if user wants to rebuild
            rebuild = input("\n    Image exists. Rebuild? (y/N): ").lower().strip()
            if rebuild != 'y':
                print("    Skipping build.")
                return

            # Remove existing image
            print("    🗑️  Removing existing image...")
            container_manager.docker_client.images.remove("codex-mcp-base:latest", force=True)

        except Exception:
            print("    📦 No existing image found.")

        print("\n[2] Building new Codex CLI image...")
        print("    This may take 2-5 minutes...")

        # Build the image
        base_image = await container_manager.ensure_base_image()

        print(f"    ✅ Build successful!")
        print(f"    Image: {base_image}")

        # Get image details
        image = container_manager.docker_client.images.get(base_image)
        print(f"    Image ID: {image.id[:12]}")
        print(f"    Size: {image.attrs['Size'] / 1024 / 1024:.1f} MB")

        print("\n[3] Testing container...")

        # Test the container
        try:
            test_container = container_manager.docker_client.containers.run(
                base_image,
                "echo 'Container test successful'",
                remove=True,
                user="codex"  # Test our user works
            )
            print("    ✅ Container test passed!")

        except Exception as e:
            print(f"    ❌ Container test failed: {e}")

        print("\n" + "=" * 50)
        print("🎉 Codex CLI container is ready!")
        print("You can now use Codex tools in Cline.")

    except Exception as e:
        print(f"\n❌ Build failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    import asyncio
    asyncio.run(build_codex_container())