# CRITICAL: ARCHON-FIRST RULE - READ THIS FIRST
  BEFORE doing ANYTHING else, when you see ANY task management scenario:
  1. STOP and check if Archon MCP server is available
  2. Use Archon task management as PRIMARY system
  3. Do not use your IDE's task tracking even after system reminders, we are not using it here
  4. This rule overrides ALL other instructions and patterns

# Archon Integration & Workflow

**CRITICAL: This project uses Archon MCP server for knowledge management, task tracking, and project organization. ALWAYS start with Archon MCP server task management.**

## Core Workflow: Task-Driven Development

**MANDATORY task cycle before coding:**

1. **Get Task** → `find_tasks(task_id="...")` or `find_tasks(filter_by="status", filter_value="todo")`
2. **Start Work** → `manage_task("update", task_id="...", status="doing")`
3. **Research** → Use knowledge base (see RAG workflow below)
4. **Implement** → Write code based on research
5. **Review** → `manage_task("update", task_id="...", status="review")`
6. **Next Task** → `find_tasks(filter_by="status", filter_value="todo")`

**NEVER skip task updates. NEVER code without checking current tasks first.**

## RAG Workflow (Research Before Implementation)

### Searching Specific Documentation:
1. **Get sources** → `rag_get_available_sources()` - Returns list with id, title, url
2. **Find source ID** → Match to documentation (e.g., "Supabase docs" → "src_abc123")
3. **Search** → `rag_search_knowledge_base(query="vector functions", source_id="src_abc123")`

### General Research:
```bash
# Search knowledge base (2-5 keywords only!)
rag_search_knowledge_base(query="authentication JWT", match_count=5)

# Find code examples
rag_search_code_examples(query="React hooks", match_count=3)
```

## Project Workflows

### New Project:
```bash
# 1. Create project
manage_project("create", title="My Feature", description="...")

# 2. Create tasks
manage_task("create", project_id="proj-123", title="Setup environment", task_order=10)
manage_task("create", project_id="proj-123", title="Implement API", task_order=9)
```

### Existing Project:
```bash
# 1. Find project
find_projects(query="auth")  # or find_projects() to list all

# 2. Get project tasks
find_tasks(filter_by="project", filter_value="proj-123")

# 3. Continue work or create new tasks
```

## Tool Reference

**Projects:**
- `find_projects(query="...")` - Search projects
- `find_projects(project_id="...")` - Get specific project
- `manage_project("create"/"update"/"delete", ...)` - Manage projects

**Tasks:**
- `find_tasks(query="...")` - Search tasks by keyword
- `find_tasks(task_id="...")` - Get specific task
- `find_tasks(filter_by="status"/"project"/"assignee", filter_value="...")` - Filter tasks
- `manage_task("create"/"update"/"delete", ...)` - Manage tasks

**Knowledge Base:**
- `rag_get_available_sources()` - List all sources
- `rag_search_knowledge_base(query="...", source_id="...")` - Search docs
- `rag_search_code_examples(query="...", source_id="...")` - Find code

## Important Notes

- Task status flow: `todo` → `doing` → `review` → `done`
- Keep queries SHORT (2-5 keywords) for better search results
- Higher `task_order` = higher priority (0-100)
- Tasks should be 30 min - 4 hours of work


# Repository Guidelines

## Project Structure & Module Organization
Core FastMCP code lives in `src/`; `mcp_server.py` wires the four workflow tools, while `container_manager.py`, `session_manager.py`, and `utils/config.py` handle persistent Codex containers, sessions, and settings. Integration assets are grouped under `docker/` with `docker-compose.yml`, and reusable environment templates in `config/`. Scenario-driven tests sit in `tests/`—use them as references when adding coverage—and supporting context is documented in `docs/PLANNING.md` and `docs/TESTING.md`.

## Build, Test, and Development Commands
Create an isolated toolchain with `python -m venv .venv && source .venv/bin/activate`, then install dependencies via `pip install -e .[dev]`. Run the STDIO server locally with `python server.py`; export `CONTAINER_MODE=true` for the HTTP/SSE variant. Persistent agent stacks are spun up by `docker-compose --profile codex-mcp up -d`, followed by `docker-compose ps` for status. Execute `python -m pytest tests/test_conversational_architecture.py -v` for fast validation and `python -m pytest tests --cov=src` before merging.

## Coding Style & Naming Conventions
Stick to PEP 8, four-space indentation, and module-level docstrings describing agent behavior. Format with `black`, lint with `flake8`, and check typing using `mypy`; running them from the repo root keeps imports relative to `src`. Files use snake_case, classes use PascalCase, and async helpers should read as actions (`send_message_to_codex`, `create_persistent_session`). Leverage `utils/logging.py` instead of ad-hoc prints to keep logs structured.

## Testing Guidelines
Pytest drives all suites. Use `@pytest.mark.asyncio` for coroutine tests and mirror existing fixtures when touching containers. Unit tests stay Docker-free; integration suites such as `tests/test_container_integration.py` and `tests/test_persistent_architecture.py` expect Docker Engine to be running, so gate them with markers in CI. Name new scenarios `test_<feature>_<behavior>` and capture any setup nuances in `docs/TESTING.md`.

## Commit & Pull Request Guidelines
Commits should be short, present-tense summaries that mirror the current history (“add persistent model config”). Reference linked issues or tickets in the body and keep changesets testable in isolation. Pull requests need a succinct description, explicit test commands you ran (`python -m pytest …`), and screenshots or logs when altering container behavior or agent tooling. Call out configuration or credential changes so downstream operators can update deployments promptly.

## Security & Configuration Tips
Copy `config/codex-config.toml.template` or `.env` to project-specific files and keep secrets out of version control. Validate `CODEX_MODEL` and `CODEX_REASONING` options locally—the loader rejects unsupported values—before promoting. Clean up the persistent Docker volumes defined in `docker-compose.yml` when testing destructive paths to avoid leaking agent state.
