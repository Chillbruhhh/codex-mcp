#!/usr/bin/env python3
"""
Test script to create an agent container and verify logging works.
"""

import asyncio
import os
import time
import docker

# Import the container manager
import sys
sys.path.insert(0, 'src')
from src.container_manager import CodexContainerManager
from src.utils.config import load_config

async def test_agent_container():
    """Test creating an agent container and check logging."""

    # Load config and create manager
    config = load_config()
    manager = CodexContainerManager(config)

    session_id = "test-session-123"
    agent_id = "test-agent-456"

    print("Creating agent container session...")

    try:
        # Create a container session
        async with manager.create_session(
            session_id=session_id,
            agent_id=agent_id,
            model="gpt-5"
        ) as session:
            print(f"✓ Container created: {session.container_name}")
            print(f"  Container ID: {session.container_id[:12]}...")

            # Wait a moment for startup
            await asyncio.sleep(3)

            # Check container logs
            client = docker.from_env()
            container = client.containers.get(session.container_id)

            print("\n" + "="*60)
            print("CONTAINER STARTUP LOGS:")
            print("="*60)
            logs = container.logs(timestamps=True).decode('utf-8')
            print(logs)
            print("="*60)

            # Test sending a message
            print("\nTesting Codex message...")
            try:
                # Set up a fake API key for testing (it will fail but we can see logging)
                session.environment['OPENAI_API_KEY'] = 'test-key-for-logging'

                response = await manager.send_message_to_codex(
                    session,
                    "Hello, this is a test message"
                )
                print(f"Response received: {response[:100]}...")

            except Exception as e:
                print(f"Expected error (no real API key): {e}")

            # Check logs again after command
            await asyncio.sleep(2)
            print("\n" + "="*60)
            print("CONTAINER LOGS AFTER COMMAND:")
            print("="*60)
            logs_after = container.logs(timestamps=True).decode('utf-8')
            # Show only new logs
            if len(logs_after) > len(logs):
                new_logs = logs_after[len(logs):]
                print(new_logs)
            else:
                print("No new logs found")
            print("="*60)

    except Exception as e:
        print(f"Error creating session: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_agent_container())