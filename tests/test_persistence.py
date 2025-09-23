#!/usr/bin/env python3
"""
Test persistent conversation context across multiple messages.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.container_manager import CodexContainerManager
from src.utils.config import get_config

async def test_persistence():
    """Test persistent conversation context."""
    print("Testing Persistent Conversation Context")
    print("=" * 50)

    try:
        # Initialize container manager
        config = get_config()
        container_manager = CodexContainerManager(config)

        print("[1] Container manager initialized")

        # Create persistent session
        print("\n[2] Creating persistent session...")
        session = await container_manager._create_persistent_session(
            session_id="persistence_test_001",
            agent_id="persistence_agent",
            model="gpt-5",
            provider="openai",
            approval_mode="suggest"
        )
        print(f"    Session created: {session.session_id}")
        print(f"    Container ID: {session.container_id[:12]}...")

        # Test sequence: multiple related messages to verify context
        messages = [
            "Create a file called test.txt with the content 'Hello World'",
            "Now add the current date to that file",
            "Show me the contents of test.txt"
        ]

        responses = []

        for i, message in enumerate(messages, 1):
            print(f"\n[{i+2}] Sending message {i}: {message[:50]}...")

            response = await container_manager.send_message_to_codex(
                session=session,
                message=message,
                timeout=60
            )

            # Store response for analysis
            responses.append(response)
            print(f"    Response length: {len(response)} characters")

            # Show first few lines of response
            response_lines = response.split('\n')[:3]
            for line in response_lines:
                if line.strip():
                    print(f"    -> {line.strip()[:100]}")

        # Analyze responses for context persistence
        print(f"\n[{len(messages)+3}] Analyzing context persistence...")

        # Check if later responses reference earlier actions
        context_indicators = [
            "test.txt",  # File should be referenced across messages
            "Hello World",  # Original content should be maintained
            "date"  # Date addition should be maintained
        ]

        context_maintained = True
        for i, response in enumerate(responses[1:], 1):  # Skip first response
            response_lower = response.lower()
            found_context = any(indicator.lower() in response_lower for indicator in context_indicators)

            if found_context:
                print(f"    ✅ Message {i+1} shows context awareness")
            else:
                print(f"    ❌ Message {i+1} may not show context awareness")
                context_maintained = False

        if context_maintained:
            print("\n🎉 SUCCESS: Persistent conversation context appears to be working!")
        else:
            print("\n⚠️  WARNING: Context persistence may need investigation")

        # Test final verification - ask about the whole sequence
        print(f"\n[{len(messages)+4}] Final context verification...")
        final_message = "What files did we create and what do they contain?"

        final_response = await container_manager.send_message_to_codex(
            session=session,
            message=final_message,
            timeout=60
        )

        print(f"    Final response length: {len(final_response)} characters")
        if "test.txt" in final_response.lower() and "hello world" in final_response.lower():
            print("    ✅ Final verification shows excellent context retention!")
        else:
            print("    ⚠️  Final verification shows limited context retention")

    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        print(f"\n[{len(messages)+5}] Cleaning up...")
        await container_manager.cleanup_all_sessions()
        print("    Cleanup complete")

if __name__ == "__main__":
    asyncio.run(test_persistence())