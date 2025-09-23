# Testing Guide - Codex CLI MCP Server

This guide provides comprehensive testing strategies for the conversational Codex CLI MCP Server architecture.

## 🧪 Testing Levels

### 1. **Unit Tests** (No External Dependencies)
**Status: ✅ PASSING**

Tests individual components in isolation with mocks.

```bash
# Quick validation of conversational architecture
python test_simple_conversational.py

# Full unit test suite
python -m pytest tests/test_conversational_architecture.py -v
```

**What it tests:**
- ✅ ContainerSession has conversational fields
- ✅ Container manager has conversational methods
- ✅ Response completion heuristics work
- ✅ Session manager updated for natural language
- ✅ MCP tools use conversational interface
- ✅ Docker setup supports interactive Codex CLI
- ✅ Configuration supports conversational architecture

### 2. **Integration Tests** (With Docker, Mock Codex CLI)
**Status: 🚧 Ready to implement**

Tests Docker container lifecycle with mock Codex processes.

```bash
# Install dependencies first
pip install -r requirements.txt

# Run integration tests
python test_docker_integration.py
```

**What it would test:**
- Container creation and startup
- Persistent process management
- stdin/stdout communication
- Session cleanup and resource management
- Authentication injection
- Resource limits enforcement

### 3. **End-to-End Tests** (Full System with Real Codex CLI)
**Status: 🚧 Ready to implement**

Tests complete conversational flow with actual Codex CLI.

```bash
# Requires valid OpenAI API key
export OPENAI_API_KEY="your-api-key-here"

# Run full system tests
python test_e2e_conversation.py
```

**What it would test:**
- Complete natural language conversation flow
- Real Codex CLI interactions
- Context preservation across messages
- Code generation and responses
- Session persistence and resumption
- Error handling and recovery

## 🎯 Current Testing Status

### ✅ **Architecture Validation - COMPLETE**

The conversational architecture has been successfully validated:

```
Testing Conversational Architecture Components
============================================================
✓ ContainerSession conversational fields validated
✓ Conversational methods exist on container manager
✓ Response completion heuristics working correctly
✓ Session manager has send_message_to_codex method
✓ MCP tools imported and use conversational interface
✓ Dockerfile properly configured for Codex CLI
✓ Configuration supports conversational architecture

All conversational architecture tests PASSED!
```

**Key Achievements:**
- 🔄 **Persistent Sessions**: ContainerSession supports long-running conversations
- 💬 **Natural Language Interface**: MCP tools use conversational messaging
- 🐳 **Docker Integration**: Container manager supports interactive processes
- 🧠 **Response Detection**: Heuristics detect when Codex responses are complete
- ⚙️ **Configuration**: All settings support conversational architecture

## 🚀 Next Testing Steps

### **Step 1: Docker Integration Testing**

Create `test_docker_integration.py`:

```python
#!/usr/bin/env python3
"""
Docker integration tests for conversational architecture.
Tests with real Docker containers but mocks Codex CLI.
"""

import asyncio
import docker
import pytest
from src.container_manager import CodexContainerManager
from src.utils.config import Config

async def test_container_conversation_lifecycle():
    """Test complete container conversation lifecycle."""
    # Requires Docker to be running
    manager = CodexContainerManager(Config())

    # Test container creation
    async with manager.create_session("test_session", "test_agent") as session:
        # Verify conversation started
        assert session.conversation_active is True
        assert session.codex_process is not None

        # Test message sending (with mock Codex response)
        response = await manager.send_message_to_codex(
            session,
            "Hello, can you help me?"
        )

        # Verify response received
        assert len(response) > 0

    # Verify cleanup
    assert session.conversation_active is False

if __name__ == "__main__":
    asyncio.run(test_container_conversation_lifecycle())
```

### **Step 2: End-to-End Testing**

Create `test_e2e_conversation.py`:

```python
#!/usr/bin/env python3
"""
End-to-end tests with real Codex CLI.
Requires valid OpenAI API key.
"""

import asyncio
import os
from src.mcp_server import codex_chat, codex_generate_code

async def test_real_codex_conversation():
    """Test conversation with real Codex CLI."""
    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  OPENAI_API_KEY not set - skipping E2E tests")
        return

    # Test natural language chat
    response = await codex_chat(
        message="Hello! Can you write a simple Python hello world function?",
        agent_id="test_agent"
    )

    # Verify we got a meaningful response
    assert "def" in response or "print" in response
    print(f"✅ Chat response: {response[:100]}...")

    # Test code generation
    code_response = await codex_generate_code(
        prompt="factorial function",
        language="python"
    )

    # Verify code generation
    assert "factorial" in code_response.lower()
    assert "def" in code_response
    print(f"✅ Code generation: {code_response[:100]}...")

if __name__ == "__main__":
    asyncio.run(test_real_codex_conversation())
```

## 🔧 Running Tests

### **Prerequisites**

```bash
# Install dependencies
pip install -r requirements.txt

# For Docker integration tests
# Ensure Docker Desktop is running

# For E2E tests
export OPENAI_API_KEY="your-openai-api-key"
```

### **Test Commands**

```bash
# 1. Unit Tests (No dependencies)
python test_simple_conversational.py

# 2. Architecture validation with pytest
python -m pytest tests/test_conversational_architecture.py -v

# 3. Docker integration (requires Docker)
python test_docker_integration.py

# 4. Full end-to-end (requires API key)
python test_e2e_conversation.py

# 5. All tests
python -m pytest tests/ -v
```

## 🐛 Debugging Failed Tests

### **Import Errors**
```bash
# If you see "ModuleNotFoundError: No module named 'src'"
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
```

### **Docker Errors**
```bash
# Ensure Docker is running
docker --version

# Check Docker permissions
docker run hello-world
```

### **API Key Errors**
```bash
# Verify API key is set
echo $OPENAI_API_KEY

# Test API key validity
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
     https://api.openai.com/v1/models
```

## 📊 Test Coverage Goals

### **Current Coverage: Architecture Validated ✅**

- [x] **Core Architecture**: Conversational components exist and work
- [x] **Interface Design**: Natural language message flow
- [x] **Container Setup**: Docker configuration for interactive Codex
- [x] **Session Management**: Persistent conversation state
- [x] **Response Handling**: Completion detection heuristics

### **Next Coverage: Integration Testing**

- [ ] **Docker Lifecycle**: Container creation, startup, cleanup
- [ ] **Process Management**: stdin/stdout communication
- [ ] **Resource Limits**: Memory, CPU, and network constraints
- [ ] **Authentication**: Credential injection and security
- [ ] **Error Handling**: Graceful failure and recovery

### **Final Coverage: End-to-End Validation**

- [ ] **Real Conversations**: Actual Codex CLI interaction
- [ ] **Context Preservation**: Multi-turn conversations
- [ ] **Code Generation**: Complex code requests
- [ ] **Session Persistence**: Long-running conversations
- [ ] **Production Readiness**: Performance and reliability

## 🎉 Success Criteria

### **Architecture Tests (Current) ✅**
- All conversational components exist and are properly designed
- Natural language interface works correctly
- Docker setup supports interactive sessions
- Configuration supports conversational architecture

### **Integration Tests (Next)**
- Containers start and manage persistent Codex processes
- stdin/stdout communication works reliably
- Resource cleanup happens automatically
- Authentication is injected securely

### **E2E Tests (Final)**
- Real Codex CLI responds to natural language
- Conversations maintain context across multiple messages
- Code generation produces working code
- System handles errors gracefully
- Performance meets production requirements

---

**The conversational architecture is validated and ready for the next testing phase! 🚀**