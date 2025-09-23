#!/usr/bin/env python3
"""
Debug where the hanging is occurring.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.container_manager import CodexContainerManager
from src.utils.config import get_config

async def debug_hanging():
    """Debug where the process is hanging."""
    print("Debug: Container Creation Process")
    print("=" * 40)

    try:
        # Initialize container manager
        config = get_config()
        container_manager = CodexContainerManager(config)

        print("[1] Container manager initialized")

        # Test 1: Check if base image exists
        print("\n[2] Checking base image...")
        try:
            base_image = await container_manager.ensure_base_image()
            print(f"    Base image ready: {base_image}")
        except Exception as e:
            print(f"    Base image failed: {e}")
            return

        # Test 2: Try creating a persistent session
        print("\n[3] Creating persistent session...")
        try:
            session = await container_manager._create_persistent_session(
                session_id="debug_session_001",
                agent_id="debug_agent",
                model="gpt-5",
                provider="openai",
                approval_mode="suggest"
            )
            print(f"    Session created: {session.session_id}")
            print(f"    Container ID: {session.container_id[:12]}...")

            # Test 3: Try sending a simple message
            print("\n[4] Testing message sending...")
            response = await container_manager.send_message_to_codex(
                session=session,
                message="hello",
                timeout=30  # Shorter timeout for testing
            )
            print(f"    Response: {response[:100]}...")

        except Exception as e:
            print(f"    Session creation/messaging failed: {e}")

        # Cleanup
        print("\n[5] Cleaning up...")
        await container_manager.cleanup_all_sessions()
        print("    Cleanup complete")

    except Exception as e:
        print(f"Debug failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_hanging())