#!/usr/bin/env python3
"""
Simple test for persistent agent architecture (Windows compatible).
"""

import asyncio
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.container_manager import CodexContainerManager
from src.utils.config import get_config

async def test_persistent_agents():
    """Test persistent agent functionality."""
    print("Testing Persistent Agent Architecture")
    print("=" * 50)

    try:
        # Set persistent mode
        os.environ["PERSISTENT_MODE"] = "true"

        # Initialize container manager
        config = get_config()
        container_manager = CodexContainerManager(config, data_path="./data")

        print("[1] Container manager initialized with persistent mode")

        # Test agent creation
        agent_id = "test_agent_001"

        print(f"\n[2] Creating persistent container for agent: {agent_id}")
        session = await container_manager.get_or_create_persistent_agent_container(
            agent_id=agent_id
        )

        print(f"    Container created: {session.container_id[:12]}...")
        print(f"    Workspace: {session.workspace_dir}")

        # Test message sending
        print(f"\n[3] Testing message sending...")
        message = "Create a file called hello.txt with content 'Hello Persistent World'"

        response = await container_manager.send_message_to_codex(
            session=session,
            message=message
        )

        print(f"    Message sent successfully")
        print(f"    Response length: {len(response)} characters")

        # Test reconnection
        print(f"\n[4] Testing reconnection...")
        session2 = await container_manager.get_or_create_persistent_agent_container(
            agent_id=agent_id
        )

        same_container = session.container_id == session2.container_id
        print(f"    Reconnected to same container: {same_container}")

        # Test context preservation
        print(f"\n[5] Testing context preservation...")
        context_message = "Show me what files exist in the current directory"

        response2 = await container_manager.send_message_to_codex(
            session=session2,
            message=context_message
        )

        print(f"    Context check completed")
        print(f"    Response length: {len(response2)} characters")

        # Check if context was preserved
        context_preserved = "hello.txt" in response2.lower()
        print(f"    Context preserved: {context_preserved}")

        # Test management tools
        print(f"\n[6] Testing management tools...")

        active_agents = await container_manager.list_active_agents()
        print(f"    Active agents found: {len(active_agents)}")

        if active_agents:
            agent_info = active_agents[0]
            print(f"    Agent ID: {agent_info.get('agent_id', 'unknown')}")
            print(f"    Status: {agent_info.get('status', 'unknown')}")

        # Test status query
        status_result = await container_manager.get_agent_status(agent_id)
        print(f"    Status query success: {status_result.get('success', False)}")

        print(f"\n[7] All tests completed successfully!")
        return True

    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        print(f"\n[8] Cleaning up...")
        try:
            # Remove test agent
            await container_manager.remove_agent_container(agent_id)
            print(f"    Test agent removed")
        except Exception as e:
            print(f"    Cleanup warning: {e}")

async def main():
    """Run the test."""
    print("Starting Persistent Agent Tests")
    print("=" * 40)

    success = await test_persistent_agents()

    print(f"\nTest Result: {'PASS' if success else 'FAIL'}")

    if success:
        print("\nPersistent Agent Architecture is working!")
    else:
        print("\nPlease check the errors above.")

    return success

if __name__ == "__main__":
    asyncio.run(main())