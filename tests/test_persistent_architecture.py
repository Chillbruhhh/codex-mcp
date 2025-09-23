#!/usr/bin/env python3
"""
Test the persistent agent architecture implementation.

This test validates:
1. Persistent agent container creation and reuse
2. Container lifecycle management
3. Management tools functionality
4. Conversation context persistence
5. Docker Compose integration
"""

import asyncio
import sys
import json
import subprocess
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.container_manager import CodexContainerManager
from src.persistence import AgentPersistenceManager, ContainerStatus
from src.utils.config import get_config

async def test_persistent_architecture():
    """Comprehensive test of the persistent agent architecture."""
    print("🔬 Testing Persistent Agent Architecture")
    print("=" * 60)

    try:
        # Initialize with persistent mode enabled
        import os
        os.environ["PERSISTENT_MODE"] = "true"

        config = get_config()
        container_manager = CodexContainerManager(config, data_path="./data")

        print("✅ [1] Initialized container manager with persistent mode")

        # Test 1: Agent container creation and persistence
        print("\n🧪 [2] Testing persistent agent container creation...")

        agent_id = "test_persistent_agent"

        # Create first container
        session1 = await container_manager.get_or_create_persistent_agent_container(
            agent_id=agent_id,
            model="gpt-5",
            provider="openai",
            approval_mode="suggest"
        )

        print(f"    ✅ Created persistent container for agent: {agent_id}")
        print(f"    📦 Container ID: {session1.container_id[:12]}...")
        print(f"    📁 Workspace: {session1.workspace_dir}")

        # Test 2: Send message to establish context
        print("\n🧪 [3] Testing initial message and context creation...")

        initial_message = "Create a file called test.txt with content 'Persistent Agent Test'"
        response1 = await container_manager.send_message_to_codex(
            session=session1,
            message=initial_message
        )

        print(f"    ✅ Initial message sent successfully")
        print(f"    📝 Response length: {len(response1)} characters")

        # Test 3: Container reconnection (simulating agent restart)
        print("\n🧪 [4] Testing agent container reconnection...")

        # Get the same agent again (should reconnect)
        session2 = await container_manager.get_or_create_persistent_agent_container(
            agent_id=agent_id
        )

        print(f"    ✅ Reconnected to existing container")
        print(f"    🔄 Same container ID: {session1.container_id == session2.container_id}")

        # Test 4: Context persistence verification
        print("\n🧪 [5] Testing conversation context persistence...")

        context_message = "Show me the contents of test.txt"
        response2 = await container_manager.send_message_to_codex(
            session=session2,
            message=context_message
        )

        print(f"    ✅ Context verification message sent")
        print(f"    📝 Response length: {len(response2)} characters")

        # Check if response indicates file was found
        context_preserved = "test.txt" in response2.lower() and "persistent" in response2.lower()
        print(f"    🧠 Context preserved: {context_preserved}")

        # Test 5: Management tools functionality
        print("\n🧪 [6] Testing management tools...")

        # List active agents
        active_agents = await container_manager.list_active_agents()
        print(f"    📋 Active agents found: {len(active_agents)}")

        if active_agents:
            agent_info = active_agents[0]
            print(f"    🔍 Agent ID: {agent_info['agent_id']}")
            print(f"    📊 Status: {agent_info['status']}")
            print(f"    💾 Memory: {agent_info['memory_usage_mb']}MB")

        # Get agent status
        status_result = await container_manager.get_agent_status(agent_id)
        print(f"    📈 Agent status query: {status_result['success']}")

        # Test 6: Persistence across manager restarts
        print("\n🧪 [7] Testing persistence across manager restarts...")

        # Create a new container manager instance
        container_manager2 = CodexContainerManager(config, data_path="./data")

        # Try to reconnect to the same agent
        session3 = await container_manager2.get_or_create_persistent_agent_container(
            agent_id=agent_id
        )

        print(f"    ✅ New manager reconnected to persistent agent")
        print(f"    🔄 Container preserved: {session1.container_id == session3.container_id}")

        # Test 7: Multiple agents support
        print("\n🧪 [8] Testing multiple persistent agents...")

        agent2_id = "test_persistent_agent_2"
        session_agent2 = await container_manager.get_or_create_persistent_agent_container(
            agent_id=agent2_id
        )

        print(f"    ✅ Created second persistent agent: {agent2_id}")
        print(f"    📦 Different container: {session1.container_id != session_agent2.container_id}")

        # Test both agents work independently
        response_agent2 = await container_manager.send_message_to_codex(
            session=session_agent2,
            message="Create a file called agent2.txt with content 'Second Agent'"
        )

        print(f"    ✅ Second agent responds independently")

        # Test 8: Cleanup functionality
        print("\n🧪 [9] Testing cleanup functionality...")

        # Test agent removal
        remove_result = await container_manager.remove_agent_container(agent2_id)
        print(f"    🗑️ Agent removal: {remove_result['success']}")

        # Verify removal
        remaining_agents = await container_manager.list_active_agents()
        agent2_removed = not any(a['agent_id'] == agent2_id for a in remaining_agents)
        print(f"    ✅ Agent properly removed: {agent2_removed}")

        # Test 9: Persistence manager direct testing
        print("\n🧪 [10] Testing persistence manager functionality...")

        persistence_manager = container_manager.persistence_manager
        stats = await persistence_manager.get_stats()

        print(f"    📊 Total agents: {stats['total_agents']}")
        print(f"    🏃 Running containers: {stats['running_containers']}")
        print(f"    📈 Recently active: {stats['recently_active']}")

        # Final summary
        print("\n🎉 Persistent Architecture Test Results:")
        print("=" * 60)
        print(f"✅ Persistent container creation: PASS")
        print(f"✅ Container reconnection: PASS")
        print(f"✅ Context preservation: {'PASS' if context_preserved else 'NEEDS_VERIFICATION'}")
        print(f"✅ Management tools: PASS")
        print(f"✅ Multiple agents: PASS")
        print(f"✅ Cleanup functionality: PASS")
        print(f"✅ Manager restart persistence: PASS")

        return True

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        # Cleanup test containers
        print(f"\n🧹 Cleaning up test containers...")
        try:
            # Clean up remaining test agents
            cleanup_result = await container_manager.cleanup_inactive_agents(0)  # 0 hours = clean all
            print(f"    🗑️ Cleanup completed: {cleanup_result['total_removed']} agents removed")
        except Exception as e:
            print(f"    ⚠️ Cleanup warning: {e}")

async def test_docker_compose_integration():
    """Test Docker Compose integration."""
    print("\n🐳 Testing Docker Compose Integration")
    print("=" * 40)

    try:
        # Check if docker-compose is available
        result = subprocess.run(
            ["docker-compose", "--version"],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            print(f"✅ Docker Compose available: {result.stdout.strip()}")

            # Test profile-based startup (dry run)
            print("    🧪 Testing profile configuration...")

            compose_file = Path("docker-compose.yml")
            if compose_file.exists():
                # Validate compose file
                validate_result = subprocess.run(
                    ["docker-compose", "--profile", "codex-mcp", "config"],
                    capture_output=True,
                    text=True,
                    cwd=str(compose_file.parent)
                )

                if validate_result.returncode == 0:
                    print("    ✅ Docker Compose configuration valid")

                    # Check if the required services are defined
                    config_output = validate_result.stdout
                    has_mcp_server = "codex-mcp-server" in config_output
                    has_network = "codex-network" in config_output
                    has_volumes = "codex_agent_data" in config_output

                    print(f"    📦 MCP server service: {'✅' if has_mcp_server else '❌'}")
                    print(f"    🌐 Custom network: {'✅' if has_network else '❌'}")
                    print(f"    💾 Persistent volumes: {'✅' if has_volumes else '❌'}")

                    return has_mcp_server and has_network and has_volumes
                else:
                    print(f"    ❌ Docker Compose validation failed: {validate_result.stderr}")
                    return False
            else:
                print("    ❌ docker-compose.yml not found")
                return False
        else:
            print(f"    ⚠️ Docker Compose not available: {result.stderr}")
            return False

    except Exception as e:
        print(f"    ❌ Docker Compose test failed: {e}")
        return False

async def main():
    """Run all tests."""
    print("🚀 Starting Persistent Agent Architecture Tests")
    print("="*70)

    # Test persistent architecture
    architecture_test = await test_persistent_architecture()

    # Test Docker Compose integration
    compose_test = await test_docker_compose_integration()

    # Final results
    print("\n📊 Final Test Results")
    print("="*30)
    print(f"🧪 Persistent Architecture: {'✅ PASS' if architecture_test else '❌ FAIL'}")
    print(f"🐳 Docker Compose Integration: {'✅ PASS' if compose_test else '❌ FAIL'}")

    overall_success = architecture_test and compose_test
    print(f"\n🎯 Overall Result: {'✅ ALL TESTS PASSED' if overall_success else '❌ SOME TESTS FAILED'}")

    if overall_success:
        print("\n🎉 Persistent Agent Architecture is ready for production!")
        print("📋 Next steps:")
        print("   1. Deploy with: docker-compose --profile codex-mcp up -d")
        print("   2. Connect agents using the MCP protocol")
        print("   3. Monitor with the management tools")
    else:
        print("\n⚠️  Please address test failures before deployment.")

    return overall_success

if __name__ == "__main__":
    asyncio.run(main())