#!/usr/bin/env python3
"""
Test network configuration for Codex CLI containers.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.container_manager import CodexContainerManager
from src.utils.config import get_config

async def test_network_config():
    """Test that Codex CLI containers are created on the correct network."""
    print("Testing Network Configuration")
    print("=" * 50)

    try:
        # Set persistent mode
        os.environ["PERSISTENT_MODE"] = "true"

        # Initialize container manager
        config = get_config()
        container_manager = CodexContainerManager(config, data_path="./data")

        print(f"[1] Container manager initialized")
        print(f"    Network mode: {config.container.network_mode}")

        # Create a test agent container
        agent_id = "network_test_agent"
        print(f"[2] Creating container for agent: {agent_id}")

        session = await container_manager.get_or_create_persistent_agent_container(
            agent_id=agent_id,
            model="gpt-5",
            provider="openai",
            approval_mode="suggest"
        )

        print(f"    Container created: {session.container_id[:12]}...")
        print(f"    Container name: {session.container_name}")

        # Print instructions for manual verification
        print(f"\n[3] Container is running! Inspect its network with:")
        print(f"    docker inspect {session.container_id[:12]} | grep NetworkMode")
        print(f"    docker network inspect codex-mcp-network")

        print(f"\n[4] Press Enter to cleanup and exit...")
        input()

        # Cleanup
        await container_manager.remove_agent_container(agent_id)
        print(f"[5] Container cleaned up")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_network_config())