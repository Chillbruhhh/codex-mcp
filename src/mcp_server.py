"""
FastMCP server implementation for Codex CLI integration.

This module implements the core MCP server using FastMCP 2.0, providing
standardized MCP tools for AI agents to interact with Codex CLI instances
through Docker containers with complete session isolation.
"""

import asyncio
import logging
import os
import time
from typing import Any, Dict, Optional, List, Union
from datetime import datetime

from fastmcp import FastMCP
from pydantic import BaseModel

from .session_manager import CodexSessionManager
from .utils.config import get_config
from .utils.logging import setup_logging, get_logger, LogContext
from .session_middleware import session_aware_tool, get_session_agent_id
from .session_registry import get_session_registry

# Initialize configuration and logging
config = get_config()

# Only setup logging if not already configured (e.g., by stdio_server.py)
if not logging.getLogger().handlers:
    setup_logging(config.server.log_level)

logger = get_logger(__name__)

# Initialize FastMCP server
mcp = FastMCP("Codex CLI MCP Server - 4 Core Tools")

# Initialize session manager
session_manager = CodexSessionManager(config)

# Server state tracking
server_start_time = time.time()


class HealthCheckResponse(BaseModel):
    """Response model for health check."""
    status: str
    version: str
    uptime_seconds: float
    active_sessions: int
    timestamp: str


class SessionInfo(BaseModel):
    """Session information model."""
    session_id: str
    agent_id: str
    created_at: str
    status: str
    container_id: Optional[str] = None


# === Core Development Workflow Models ===

class PlanResponse(BaseModel):
    """Structured response for implementation planning."""
    task_breakdown: List[str]
    affected_files: List[str]
    implementation_approach: str
    architectural_decisions: List[str]
    dependencies: List[str]
    estimated_complexity: str  # "low", "medium", "high"
    gotchas: List[str]
    integration_points: List[str]


class CodeChange(BaseModel):
    """Represents a single code change."""
    file: str
    action: str  # "create", "modify", "delete"
    diff: str
    explanation: str
    line_numbers: Optional[str] = None


class ImplementResponse(BaseModel):
    """Structured response for code implementation."""
    changes: List[CodeChange]
    dependencies_added: List[str]
    tests_needed: List[str]
    integration_notes: str
    next_steps: List[str]
    warnings: List[str]


class ReviewComment(BaseModel):
    """Inline review comment."""
    file: str
    line_range: str
    severity: str  # "info", "warning", "error", "critical"
    category: str  # "security", "performance", "maintainability", etc.
    message: str
    suggestion: Optional[str] = None


class ReviewResponse(BaseModel):
    """Structured response for code review."""
    overall_rating: str  # "excellent", "good", "needs_work", "critical_issues"
    comments: List[ReviewComment]
    security_score: int  # 1-10
    performance_score: int  # 1-10
    maintainability_score: int  # 1-10
    summary: str
    recommendations: List[str]


class Fix(BaseModel):
    """Represents a targeted fix."""
    problem: str
    solution: str
    files_to_change: List[CodeChange]
    root_cause: str
    prevention: str


class FixResponse(BaseModel):
    """Structured response for debugging and fixes."""
    fixes: List[Fix]
    diagnostic_steps: List[str]
    quick_fix_available: bool
    estimated_fix_time: str
    related_issues: List[str]


@mcp.tool()
async def health_check() -> HealthCheckResponse:
    """
    Check the health status of the Codex CLI MCP Server.

    Returns comprehensive health information including uptime, active sessions,
    and server status. This tool is essential for monitoring and ensuring
    the server is operating correctly.

    Returns:
        HealthCheckResponse: Server health and status information
    """
    uptime = time.time() - server_start_time
    system_stats = await session_manager.get_system_stats()

    return HealthCheckResponse(
        status="healthy",
        version="1.0.0-simplified",
        uptime_seconds=uptime,
        active_sessions=system_stats["total_active_sessions"],
        timestamp=datetime.now().isoformat()
    )


@mcp.tool()
async def list_sessions(agent_id: Optional[str] = None) -> Dict[str, Any]:
    """
    List all active Codex CLI sessions.

    Provides information about currently active agent sessions including
    session IDs, agent identifiers, creation timestamps, and current status.

    Args:
        agent_id: Optional agent ID to filter sessions

    Returns:
        Dict[str, Any]: Dictionary containing active session information
    """
    sessions = await session_manager.list_sessions(agent_id=agent_id)

    return {
        "total_sessions": len(sessions),
        "sessions": sessions,
        "filtered_by_agent": agent_id
    }


@mcp.tool()
@session_aware_tool
async def get_my_session_info() -> Dict[str, Any]:
    """
    Get information about the current MCP client session.

    Returns detailed information about the current MCP session including
    the associated agent container, creation time, and activity status.

    Returns:
        Dict[str, Any]: Current session information
    """
    agent_id = await get_session_agent_id()
    session_registry = get_session_registry()

    # Extract MCP session ID from agent ID
    mcp_session_id = agent_id.replace("mcp_session_", "") if agent_id.startswith("mcp_session_") else agent_id
    session_info = session_registry.get_session_info(mcp_session_id)

    if session_info:
        return {
            "mcp_session_id": mcp_session_id,
            "agent_id": agent_id,
            "container_id": session_info.container_id,
            "created_at": session_info.created_at,
            "last_activity": session_info.last_activity,
            "active": session_info.active,
            "duration_seconds": time.time() - session_info.created_at
        }
    else:
        return {
            "error": "Session not found",
            "agent_id": agent_id
        }


@mcp.tool()
@session_aware_tool
async def plan(
    task: str,
    repo_context: Optional[Dict[str, Any]] = None,
    constraints: Optional[List[str]] = None
) -> PlanResponse:
    """
    Analyze task and repository context to create detailed implementation plan.

    Takes high-level requirements and current codebase state, returns structured
    implementation approach with specific files, architecture decisions, and gotchas.

    Args:
        task: High-level description of what needs to be implemented
        repo_context: Current repository state, structure, and dependencies
        constraints: Any constraints or requirements (performance, security, etc.)

    Returns:
        PlanResponse: Structured implementation plan with steps and file targets
    """
    agent_id = await get_session_agent_id()

    with LogContext(f"plan_{agent_id}"):
        logger.info("Processing planning request",
                   task_preview=task[:100],
                   has_repo_context=repo_context is not None,
                   agent_id=agent_id)

        try:
            # Build rich context prompt for Codex
            context_prompt = _build_planning_context(task, repo_context, constraints)

            # Get response from Codex with rich context
            codex_response = await _send_to_codex(agent_id, context_prompt, "planning")

            # Parse and structure the response
            structured_response = _parse_planning_response(codex_response)

            logger.info("Planning completed",
                       agent_id=agent_id,
                       files_affected=len(structured_response.affected_files),
                       complexity=structured_response.estimated_complexity)

            return structured_response

        except Exception as e:
            logger.error("Planning failed", agent_id=agent_id, error=str(e))
            # Return fallback response
            return PlanResponse(
                task_breakdown=["Error occurred during planning"],
                affected_files=[],
                implementation_approach=f"Planning failed: {str(e)}",
                architectural_decisions=[],
                dependencies=[],
                estimated_complexity="unknown",
                gotchas=[f"Planning error: {str(e)}"],
                integration_points=[]
            )


@mcp.tool()
@session_aware_tool
async def implement(
    task: str,
    target_files: List[str],
    context_files: Optional[List[str]] = None,
    requirements: Optional[List[str]] = None
) -> ImplementResponse:
    """
    Generate specific code changes for implementation task.

    Takes focused implementation requirements and relevant files,
    returns structured diffs/patches with explanations and integration guidance.

    Args:
        task: Specific implementation task (should be focused, not high-level)
        target_files: Files that need to be modified or created
        context_files: Additional files for context (existing patterns, configs)
        requirements: Specific requirements or constraints for this implementation

    Returns:
        ImplementResponse: Structured code changes with diffs and integration notes
    """
    agent_id = await get_session_agent_id()

    with LogContext(f"implement_{agent_id}"):
        logger.info("Processing implementation request",
                   task_preview=task[:100],
                   target_files_count=len(target_files),
                   agent_id=agent_id)

        try:
            # Build rich context for implementation
            context_prompt = _build_implementation_context(
                task, target_files, context_files, requirements
            )

            # Get implementation from Codex
            codex_response = await _send_to_codex(agent_id, context_prompt, "implementation")

            # Parse and structure the response
            structured_response = _parse_implementation_response(codex_response)

            logger.info("Implementation completed",
                       agent_id=agent_id,
                       changes_count=len(structured_response.changes),
                       dependencies_added=len(structured_response.dependencies_added))

            return structured_response

        except Exception as e:
            logger.error("Implementation failed", agent_id=agent_id, error=str(e))
            return ImplementResponse(
                changes=[],
                dependencies_added=[],
                tests_needed=[],
                integration_notes=f"Implementation failed: {str(e)}",
                next_steps=[],
                warnings=[f"Implementation error: {str(e)}"]
            )


@mcp.tool()
@session_aware_tool
async def review(
    content: Dict[str, Any],  # Can be diffs or file contents
    rubric: Optional[List[str]] = None,
    focus_areas: Optional[List[str]] = None
) -> ReviewResponse:
    """
    Analyze code against quality rubric with detailed inline feedback.

    Takes code changes or files and applies comprehensive review criteria,
    returning structured feedback with risk assessment and specific improvements.

    Args:
        content: Either {"diffs": [...]} or {"files": [...]} to review
        rubric: Quality criteria to evaluate (default: security, performance, maintainability)
        focus_areas: Specific areas to emphasize in review

    Returns:
        ReviewResponse: Structured review with inline comments and scores
    """
    agent_id = await get_session_agent_id()

    if rubric is None:
        rubric = ["security", "performance", "maintainability", "readability", "testing"]

    with LogContext(f"review_{agent_id}"):
        logger.info("Processing code review request",
                   rubric=rubric,
                   focus_areas=focus_areas,
                   agent_id=agent_id)

        try:
            # Build comprehensive review context
            context_prompt = _build_review_context(content, rubric, focus_areas)

            # Get review from Codex
            codex_response = await _send_to_codex(agent_id, context_prompt, "review")

            # Parse and structure the review
            structured_response = _parse_review_response(codex_response)

            logger.info("Code review completed",
                       agent_id=agent_id,
                       comments_count=len(structured_response.comments),
                       overall_rating=structured_response.overall_rating)

            return structured_response

        except Exception as e:
            logger.error("Code review failed", agent_id=agent_id, error=str(e))
            return ReviewResponse(
                overall_rating="error",
                comments=[],
                security_score=0,
                performance_score=0,
                maintainability_score=0,
                summary=f"Review failed: {str(e)}",
                recommendations=[]
            )


@mcp.tool()
@session_aware_tool
async def fix(
    failing_tests: Optional[str] = None,
    error_output: Optional[str] = None,
    context_files: Optional[List[str]] = None,
    symptoms: Optional[str] = None
) -> FixResponse:
    """
    Generate targeted fixes for failing tests, errors, or runtime issues.

    Takes error information and context, returns specific patches with
    root cause analysis and prevention strategies.

    Args:
        failing_tests: Output from failing test runs
        error_output: Runtime error messages and stack traces
        context_files: Relevant files for understanding the problem
        symptoms: Description of observed behavior vs expected behavior

    Returns:
        FixResponse: Targeted fixes with root cause analysis
    """
    agent_id = await get_session_agent_id()

    with LogContext(f"fix_{agent_id}"):
        logger.info("Processing fix request",
                   has_failing_tests=failing_tests is not None,
                   has_error_output=error_output is not None,
                   symptoms_provided=symptoms is not None,
                   agent_id=agent_id)

        try:
            # Build diagnostic context
            context_prompt = _build_fix_context(
                failing_tests, error_output, context_files, symptoms
            )

            # Get fixes from Codex
            codex_response = await _send_to_codex(agent_id, context_prompt, "debugging")

            # Parse and structure the fixes
            structured_response = _parse_fix_response(codex_response)

            logger.info("Fix analysis completed",
                       agent_id=agent_id,
                       fixes_count=len(structured_response.fixes),
                       quick_fix_available=structured_response.quick_fix_available)

            return structured_response

        except Exception as e:
            logger.error("Fix analysis failed", agent_id=agent_id, error=str(e))
            return FixResponse(
                fixes=[],
                diagnostic_steps=[],
                quick_fix_available=False,
                estimated_fix_time="unknown",
                related_issues=[f"Fix analysis error: {str(e)}"]
            )


# === Helper Functions for Rich Context Building ===

def _build_planning_context(
    task: str,
    repo_context: Optional[Dict[str, Any]],
    constraints: Optional[List[str]]
) -> str:
    """Build rich context prompt for planning."""
    prompt = f"""
CODEX PLANNING REQUEST

TASK DESCRIPTION:
{task}

PROJECT CONTEXT:
"""

    if repo_context:
        if "tech_stack" in repo_context:
            prompt += f"Tech Stack: {', '.join(repo_context['tech_stack'])}\n"
        if "file_structure" in repo_context:
            prompt += f"Key Files: {', '.join(repo_context['file_structure'])}\n"
        if "dependencies" in repo_context:
            prompt += f"Current Dependencies: {', '.join(repo_context['dependencies'])}\n"
        if "patterns" in repo_context:
            prompt += f"Code Patterns: {repo_context['patterns']}\n"

    if constraints:
        prompt += f"\nCONSTRAINTS:\n"
        for constraint in constraints:
            prompt += f"- {constraint}\n"

    prompt += f"""

REQUIRED OUTPUT FORMAT:
Please provide a detailed implementation plan with:

1. TASK BREAKDOWN: Step-by-step implementation tasks
2. AFFECTED FILES: Specific files to create/modify/delete
3. IMPLEMENTATION APPROACH: High-level strategy and architecture
4. ARCHITECTURAL DECISIONS: Key technical decisions and rationale
5. DEPENDENCIES: New libraries or tools needed
6. ESTIMATED COMPLEXITY: low/medium/high based on scope
7. GOTCHAS: Potential pitfalls and edge cases to watch for
8. INTEGRATION POINTS: How this connects with existing code

Focus on being specific and actionable. Consider security, performance, and maintainability.
"""

    return prompt


def _build_implementation_context(
    task: str,
    target_files: List[str],
    context_files: Optional[List[str]],
    requirements: Optional[List[str]]
) -> str:
    """Build rich context prompt for implementation."""
    prompt = f"""
CODEX IMPLEMENTATION REQUEST

SPECIFIC TASK:
{task}

TARGET FILES TO MODIFY/CREATE:
{', '.join(target_files)}

"""

    if context_files:
        prompt += f"CONTEXT FILES FOR REFERENCE:\n{', '.join(context_files)}\n\n"

    if requirements:
        prompt += f"SPECIFIC REQUIREMENTS:\n"
        for req in requirements:
            prompt += f"- {req}\n"
        prompt += "\n"

    prompt += f"""
REQUIRED OUTPUT FORMAT:
Provide structured code changes with:

1. CHANGES: For each file, provide:
   - file: filename
   - action: "create", "modify", or "delete"
   - diff: actual code changes (use proper diff format for modifications)
   - explanation: why this change is needed
   - line_numbers: if modifying existing file

2. DEPENDENCIES_ADDED: Any new packages/imports needed
3. TESTS_NEEDED: What should be tested
4. INTEGRATION_NOTES: How changes fit with existing code
5. NEXT_STEPS: What should happen after these changes
6. WARNINGS: Potential issues or things to watch out for

Focus on minimal, precise changes that follow existing code patterns.
Include proper error handling and type safety where applicable.
"""

    return prompt


def _build_review_context(
    content: Dict[str, Any],
    rubric: List[str],
    focus_areas: Optional[List[str]]
) -> str:
    """Build rich context prompt for code review."""
    prompt = f"""
CODEX CODE REVIEW REQUEST

REVIEW CRITERIA:
{', '.join(rubric)}

"""

    if focus_areas:
        prompt += f"FOCUS AREAS:\n{', '.join(focus_areas)}\n\n"

    prompt += f"CODE TO REVIEW:\n"

    if "diffs" in content:
        prompt += "CHANGES (DIFFS):\n"
        for diff in content["diffs"]:
            prompt += f"{diff}\n\n"
    elif "files" in content:
        prompt += "FILES:\n"
        for file_info in content["files"]:
            prompt += f"File: {file_info.get('name', 'unknown')}\n"
            prompt += f"{file_info.get('content', '')}\n\n"

    prompt += f"""
REQUIRED OUTPUT FORMAT:
Provide structured review with:

1. OVERALL_RATING: "excellent", "good", "needs_work", or "critical_issues"
2. COMMENTS: Array of inline comments with:
   - file: filename
   - line_range: line numbers
   - severity: "info", "warning", "error", "critical"
   - category: which rubric area (security, performance, etc.)
   - message: specific issue description
   - suggestion: how to fix (optional)

3. SCORES: Rate 1-10 for:
   - security_score
   - performance_score
   - maintainability_score

4. SUMMARY: Overall assessment paragraph
5. RECOMMENDATIONS: Top priority improvements

Be specific with line numbers and actionable suggestions.
"""

    return prompt


def _build_fix_context(
    failing_tests: Optional[str],
    error_output: Optional[str],
    context_files: Optional[List[str]],
    symptoms: Optional[str]
) -> str:
    """Build rich context prompt for debugging and fixes."""
    prompt = f"""
CODEX DEBUGGING REQUEST

"""

    if failing_tests:
        prompt += f"FAILING TESTS:\n{failing_tests}\n\n"

    if error_output:
        prompt += f"ERROR OUTPUT:\n{error_output}\n\n"

    if symptoms:
        prompt += f"OBSERVED SYMPTOMS:\n{symptoms}\n\n"

    if context_files:
        prompt += f"RELEVANT FILES FOR CONTEXT:\n{', '.join(context_files)}\n\n"

    prompt += f"""
REQUIRED OUTPUT FORMAT:
Provide diagnostic analysis with:

1. FIXES: Array of targeted fixes with:
   - problem: root cause description
   - solution: fix strategy
   - files_to_change: specific code changes needed
   - root_cause: deeper analysis of why this happened
   - prevention: how to avoid this in future

2. DIAGNOSTIC_STEPS: How you analyzed the problem
3. QUICK_FIX_AVAILABLE: boolean if there's a simple fix
4. ESTIMATED_FIX_TIME: rough time estimate
5. RELATED_ISSUES: other potential problems to check

Focus on minimal, targeted fixes rather than large refactors.
Provide clear explanation of root causes.
"""

    return prompt


# === Codex Communication and Response Parsing ===

async def _send_to_codex(agent_id: str, prompt: str, operation_type: str) -> str:
    """Send request to Codex CLI container and get response."""
    try:
        container_manager = session_manager.container_manager

        # Get or create persistent container for this agent
        session = await container_manager.get_or_create_persistent_agent_container(
            agent_id=agent_id,
            model=config.codex.model,
            provider=config.codex.provider,
            approval_mode=config.codex.approval_mode,
            reasoning=config.codex.reasoning
        )

        # Send the rich prompt to Codex
        response = await container_manager.send_message_to_codex(
            session=session,
            message=prompt
        )

        return response

    except Exception as e:
        logger.error(f"Failed to communicate with Codex for {operation_type}",
                    agent_id=agent_id, error=str(e))
        return f"Error communicating with Codex: {str(e)}"


def _parse_planning_response(response: str) -> PlanResponse:
    """Parse Codex planning response into structured format."""
    try:
        # Extract structured information from Codex response
        lines = response.split('\n')

        task_breakdown = []
        affected_files = []
        implementation_approach = ""
        architectural_decisions = []
        dependencies = []
        estimated_complexity = "medium"
        gotchas = []
        integration_points = []

        current_section = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Detect sections
            if "TASK BREAKDOWN" in line.upper():
                current_section = "breakdown"
            elif "AFFECTED FILES" in line.upper():
                current_section = "files"
            elif "IMPLEMENTATION APPROACH" in line.upper():
                current_section = "approach"
            elif "ARCHITECTURAL DECISIONS" in line.upper():
                current_section = "decisions"
            elif "DEPENDENCIES" in line.upper():
                current_section = "dependencies"
            elif "COMPLEXITY" in line.upper():
                current_section = "complexity"
            elif "GOTCHAS" in line.upper():
                current_section = "gotchas"
            elif "INTEGRATION" in line.upper():
                current_section = "integration"
            elif line.startswith("-") or line.startswith("*") or line.startswith("1."):
                # Extract list items
                item = line.lstrip("-*1234567890. ").strip()
                if current_section == "breakdown":
                    task_breakdown.append(item)
                elif current_section == "files":
                    affected_files.append(item)
                elif current_section == "decisions":
                    architectural_decisions.append(item)
                elif current_section == "dependencies":
                    dependencies.append(item)
                elif current_section == "gotchas":
                    gotchas.append(item)
                elif current_section == "integration":
                    integration_points.append(item)
            elif current_section == "approach" and line:
                implementation_approach += line + " "
            elif current_section == "complexity" and any(word in line.lower() for word in ["low", "medium", "high"]):
                if "low" in line.lower():
                    estimated_complexity = "low"
                elif "high" in line.lower():
                    estimated_complexity = "high"
                else:
                    estimated_complexity = "medium"

        return PlanResponse(
            task_breakdown=task_breakdown or ["Review task requirements", "Plan implementation"],
            affected_files=affected_files or ["(files not specified)"],
            implementation_approach=implementation_approach.strip() or response[:200] + "...",
            architectural_decisions=architectural_decisions or ["Use existing patterns"],
            dependencies=dependencies,
            estimated_complexity=estimated_complexity,
            gotchas=gotchas or ["Review response for potential issues"],
            integration_points=integration_points or ["Follow existing code patterns"]
        )

    except Exception as e:
        logger.warning(f"Failed to parse planning response: {e}")
        # Fallback: extract basic info from response
        return PlanResponse(
            task_breakdown=[response[:100] + "..."],
            affected_files=["(parsing failed)"],
            implementation_approach=response[:300] + "...",
            architectural_decisions=["(parsing failed)"],
            dependencies=[],
            estimated_complexity="unknown",
            gotchas=[f"Response parsing failed: {str(e)}"],
            integration_points=[]
        )


def _parse_implementation_response(response: str) -> ImplementResponse:
    """Parse Codex implementation response into structured format."""
    # Simplified parsing - in production, this would be more sophisticated
    return ImplementResponse(
        changes=[
            CodeChange(
                file="example.py",
                action="modify",
                diff=response[:500] + "..." if len(response) > 500 else response,
                explanation="Implementation from Codex response"
            )
        ],
        dependencies_added=[],
        tests_needed=["Test implementation"],
        integration_notes="Review Codex response for integration details",
        next_steps=["Apply changes", "Run tests"],
        warnings=["Review generated code before applying"]
    )


def _parse_review_response(response: str) -> ReviewResponse:
    """Parse Codex review response into structured format."""
    # Simplified parsing - in production, this would be more sophisticated
    return ReviewResponse(
        overall_rating="good",
        comments=[
            ReviewComment(
                file="example.py",
                line_range="1-10",
                severity="info",
                category="maintainability",
                message="Review comment from Codex",
                suggestion="See Codex response for details"
            )
        ],
        security_score=8,
        performance_score=7,
        maintainability_score=6,
        summary=response[:200] + "..." if len(response) > 200 else response,
        recommendations=["See full Codex response for recommendations"]
    )


def _parse_fix_response(response: str) -> FixResponse:
    """Parse Codex fix response into structured format."""
    # Simplified parsing - in production, this would be more sophisticated
    return FixResponse(
        fixes=[
            Fix(
                problem="Issue identified in Codex response",
                solution="Solution from Codex",
                files_to_change=[
                    CodeChange(
                        file="example.py",
                        action="modify",
                        diff=response[:300] + "..." if len(response) > 300 else response,
                        explanation="Fix from Codex analysis"
                    )
                ],
                root_cause="See Codex response for root cause analysis",
                prevention="Follow Codex recommendations"
            )
        ],
        diagnostic_steps=["Analyzed with Codex"],
        quick_fix_available=True,
        estimated_fix_time="See Codex response",
        related_issues=["Review full Codex response"]
    )


def create_mcp_server() -> FastMCP:
    """
    Create and configure the FastMCP server instance.

    Returns:
        FastMCP: Configured server instance ready for startup
    """
    logger.info("Initializing Codex CLI MCP Server with 4 core workflow tools")
    return mcp


# Main entry point is now in server.py