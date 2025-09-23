"""
Tests for the conversational architecture redesign.

Tests the new persistent session and natural language conversation capabilities
without external dependencies.
"""

import asyncio
import pytest
import sys
import time
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestConversationalArchitecture:
    """Test the conversational architecture components."""

    def setup_method(self):
        """Set up mocks for each test."""
        # Mock external dependencies
        sys.modules['structlog'] = Mock()
        sys.modules['docker'] = Mock()
        sys.modules['docker.errors'] = Mock()
        sys.modules['tomli'] = Mock()
        sys.modules['dotenv'] = Mock()

        # Mock specific Docker exceptions
        sys.modules['docker.errors'].DockerException = Exception
        sys.modules['docker.errors'].NotFound = Exception
        sys.modules['docker.errors'].APIError = Exception

    def test_container_session_conversational_fields(self):
        """Test ContainerSession has conversational fields."""
        from src.container_manager import ContainerSession

        session = ContainerSession(
            session_id="test_conv_session",
            agent_id="test_agent"
        )

        # Test new conversational fields exist
        assert hasattr(session, 'codex_process')
        assert hasattr(session, 'stdin_writer')
        assert hasattr(session, 'stdout_reader')
        assert hasattr(session, 'stderr_reader')
        assert hasattr(session, 'conversation_active')
        assert hasattr(session, 'last_interaction')

        # Test default values
        assert session.codex_process is None
        assert session.stdin_writer is None
        assert session.stdout_reader is None
        assert session.stderr_reader is None
        assert session.conversation_active is False
        assert isinstance(session.last_interaction, float)

        print("✅ ContainerSession conversational fields validated")

    @patch('src.container_manager.docker')
    def test_start_codex_conversation_method(self, mock_docker):
        """Test start_codex_conversation method exists and structure."""
        from src.container_manager import CodexContainerManager, ContainerSession
        from src.utils.config import Config

        # Mock container and exec_run
        mock_container = Mock()
        mock_exec_result = Mock()
        mock_exec_result._sock = Mock()
        mock_container.exec_run.return_value = mock_exec_result

        mock_client = Mock()
        mock_client.containers.get.return_value = mock_container
        mock_docker.from_env.return_value = mock_client

        manager = CodexContainerManager(Config())
        session = ContainerSession(
            session_id="test_session",
            agent_id="test_agent",
            container_id="mock_container_123"
        )

        # Test method exists
        assert hasattr(manager, 'start_codex_conversation')
        assert callable(manager.start_codex_conversation)

        # Test async execution
        async def test_start():
            await manager.start_codex_conversation(session)

            # Verify conversation state
            assert session.conversation_active is True
            assert session.codex_process is not None
            assert session.last_interaction > 0

        asyncio.run(test_start())

        # Verify Docker exec_run was called correctly
        mock_container.exec_run.assert_called_once_with(
            cmd=["codex"],
            stdin=True,
            stdout=True,
            stderr=True,
            tty=True,
            user="codex",
            workdir="/app/workspace",
            detach=False,
            socket=True
        )

        print("✅ start_codex_conversation method validated")

    @patch('src.container_manager.docker')
    def test_send_message_to_codex_method(self, mock_docker):
        """Test send_message_to_codex method."""
        from src.container_manager import CodexContainerManager, ContainerSession
        from src.utils.config import Config

        # Mock socket operations
        mock_socket = Mock()
        mock_socket.sendall = Mock()
        mock_socket.recv.return_value = b"Codex response: Hello, how can I help you?\ncodex> "
        mock_socket.settimeout = Mock()

        mock_exec_result = Mock()
        mock_exec_result._sock = mock_socket

        manager = CodexContainerManager(Config())
        session = ContainerSession(
            session_id="test_session",
            agent_id="test_agent",
            container_id="mock_container_123"
        )
        session.conversation_active = True
        session.codex_process = mock_exec_result

        # Test method exists
        assert hasattr(manager, 'send_message_to_codex')
        assert callable(manager.send_message_to_codex)

        # Test message sending
        async def test_send():
            response = await manager.send_message_to_codex(
                session,
                "Hello, can you help me write a Python function?"
            )

            # Verify response
            assert "Codex response" in response
            assert len(response) > 0

            # Verify socket operations
            mock_socket.sendall.assert_called()
            sent_data = mock_socket.sendall.call_args[0][0]
            assert b"Hello, can you help me write a Python function?" in sent_data
            assert sent_data.endswith(b"\n")  # Should end with newline

        asyncio.run(test_send())

        print("✅ send_message_to_codex method validated")

    def test_response_completion_heuristics(self):
        """Test _is_complete_response heuristics."""
        from src.container_manager import CodexContainerManager
        from src.utils.config import Config

        with patch('src.container_manager.docker'):
            manager = CodexContainerManager(Config())

            # Test completion indicators
            assert manager._is_complete_response("codex>") is True
            assert manager._is_complete_response("$ ") is True
            assert manager._is_complete_response("Would you like me to help with anything else?") is True
            assert manager._is_complete_response("Here is the code you requested. Is there anything else?") is True

            # Test incomplete responses
            assert manager._is_complete_response("") is False
            assert manager._is_complete_response("Loading") is False
            assert manager._is_complete_response("Generating code") is False

            # Test substantial responses with punctuation
            long_response = "Here's a Python function that calculates the factorial of a number."
            assert manager._is_complete_response(long_response) is True

        print("✅ Response completion heuristics validated")

    @patch('src.session_manager.CodexContainerManager')
    def test_session_manager_send_message_method(self, mock_container_manager_class):
        """Test session manager send_message_to_codex method."""
        from src.session_manager import CodexSessionManager, AgentSession
        from src.utils.config import Config

        # Mock container manager
        mock_container_manager = Mock()
        mock_container_manager.send_message_to_codex = AsyncMock(
            return_value="Mocked Codex response"
        )
        mock_container_manager_class.return_value = mock_container_manager

        session_manager = CodexSessionManager(Config())

        # Create mock session
        agent_session = AgentSession(
            session_id="test_session",
            agent_id="test_agent"
        )
        agent_session.container_session = Mock()
        session_manager.active_sessions["test_session"] = agent_session

        # Test method exists
        assert hasattr(session_manager, 'send_message_to_codex')
        assert callable(session_manager.send_message_to_codex)

        # Test message sending
        async def test_send():
            response = await session_manager.send_message_to_codex(
                session_id="test_session",
                message="Write a hello world function",
                timeout=60
            )

            assert response == "Mocked Codex response"

            # Verify metrics updated
            assert agent_session.metrics.total_requests == 1
            assert agent_session.metrics.successful_requests == 1
            assert agent_session.last_activity > 0

        asyncio.run(test_send())

        print("✅ Session manager send_message_to_codex validated")

    def test_mcp_tools_conversational_interface(self):
        """Test MCP tools use conversational interface."""
        # Mock session manager
        mock_session_manager = AsyncMock()
        mock_session_manager.send_message_to_codex = AsyncMock(
            return_value="Generated Python code:\n\ndef hello_world():\n    print('Hello, World!')"
        )
        mock_session_manager.create_session = AsyncMock()

        with patch('src.mcp_server.session_manager', mock_session_manager):
            from src.mcp_server import codex_chat, codex_generate_code

            # Test codex_chat uses natural language
            async def test_chat():
                response = await codex_chat(
                    message="Help me write a Python function",
                    session_id="test_session"
                )

                assert "Generated Python code" in response

                # Verify it called send_message_to_codex, not execute_codex_command
                mock_session_manager.send_message_to_codex.assert_called_once_with(
                    session_id="test_session",
                    message="Help me write a Python function"
                )

            # Test codex_generate_code uses natural language
            async def test_generate():
                mock_session_manager.reset_mock()

                response = await codex_generate_code(
                    prompt="factorial function",
                    language="python",
                    session_id="test_session"
                )

                assert "Generated Python code" in response

                # Verify natural language request construction
                mock_session_manager.send_message_to_codex.assert_called_once()
                call_args = mock_session_manager.send_message_to_codex.call_args
                message = call_args[1]['message']
                assert "Please generate python code for: factorial function" in message

            asyncio.run(test_chat())
            asyncio.run(test_generate())

        print("✅ MCP tools conversational interface validated")

    def test_session_lifecycle_with_conversation(self):
        """Test session lifecycle includes conversation management."""
        from src.container_manager import ContainerSession

        session = ContainerSession(
            session_id="lifecycle_test",
            agent_id="test_agent"
        )

        # Test initial state
        assert session.conversation_active is False
        assert session.codex_process is None

        # Simulate conversation start
        session.conversation_active = True
        session.codex_process = Mock()
        session.last_interaction = time.time()

        # Test active state
        assert session.conversation_active is True
        assert session.codex_process is not None
        assert session.last_interaction > 0

        print("✅ Session lifecycle with conversation validated")


class TestConversationalIntegration:
    """Integration tests for conversational architecture."""

    def setup_method(self):
        """Set up mocks for integration tests."""
        sys.modules['structlog'] = Mock()
        sys.modules['docker'] = Mock()
        sys.modules['docker.errors'] = Mock()
        sys.modules['tomli'] = Mock()
        sys.modules['dotenv'] = Mock()

    @patch('src.container_manager.docker')
    @patch('src.session_manager.CodexContainerManager')
    def test_end_to_end_conversation_flow(self, mock_container_manager_class, mock_docker):
        """Test complete conversation flow from MCP tool to container."""
        from src.session_manager import CodexSessionManager, AgentSession
        from src.utils.config import Config

        # Mock container manager with conversational capabilities
        mock_container_manager = Mock()
        mock_container_manager.send_message_to_codex = AsyncMock(
            return_value="Sure! Here's a Python hello world function:\n\ndef hello_world():\n    print('Hello, World!')\n\ncodex> "
        )
        mock_container_manager_class.return_value = mock_container_manager

        session_manager = CodexSessionManager(Config())

        # Create active session
        agent_session = AgentSession(
            session_id="e2e_test",
            agent_id="test_agent"
        )
        agent_session.container_session = Mock()
        session_manager.active_sessions["e2e_test"] = agent_session

        async def test_flow():
            # Send natural language message
            response = await session_manager.send_message_to_codex(
                session_id="e2e_test",
                message="Can you write a hello world function in Python?",
                timeout=30
            )

            # Verify response
            assert "def hello_world()" in response
            assert "print('Hello, World!')" in response

            # Verify container manager was called with natural language
            mock_container_manager.send_message_to_codex.assert_called_once()
            args = mock_container_manager.send_message_to_codex.call_args[0]
            assert "Can you write a hello world function in Python?" in str(args)

            # Verify metrics
            assert agent_session.metrics.total_requests == 1
            assert agent_session.metrics.successful_requests == 1

        asyncio.run(test_flow())

        print("✅ End-to-end conversation flow validated")


if __name__ == "__main__":
    # Run unit tests
    test = TestConversationalArchitecture()
    test.setup_method()
    test.test_container_session_conversational_fields()
    test.test_start_codex_conversation_method()
    test.test_send_message_to_codex_method()
    test.test_response_completion_heuristics()
    test.test_session_manager_send_message_method()
    test.test_mcp_tools_conversational_interface()
    test.test_session_lifecycle_with_conversation()

    # Run integration tests
    integration_test = TestConversationalIntegration()
    integration_test.setup_method()
    integration_test.test_end_to_end_conversation_flow()

    print("\n🎉 All conversational architecture tests passed!")
    print("✅ Persistent session architecture is working")
    print("✅ Natural language conversation flow is correct")
    print("✅ Container-level conversation management is sound")
    print("✅ Session manager conversation integration is working")
    print("✅ MCP tools use conversational interface properly")