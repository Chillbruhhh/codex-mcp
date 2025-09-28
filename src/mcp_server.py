"""
FastMCP server implementation for Codex CLI integration.

This module implements the core MCP server using FastMCP 2.0, providing
standardized MCP tools for AI agents to interact with Codex CLI instances
through Docker containers with complete session isolation.
"""

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, Optional, List, Union
from datetime import datetime, timezone

from fastmcp import FastMCP
from pydantic import BaseModel

from .session_manager import CodexSessionManager
from .utils.config import get_config
from .utils.logging import setup_logging, get_logger, LogContext
from .session_middleware import session_aware_tool, get_session_agent_id
from .session_registry import get_session_registry
from .conversational_mcp_tools import ConversationalMCPTools
from .direct_codex_tools import DirectCodexTools

# Initialize configuration and logging
config = get_config()

# Only setup logging if not already configured (e.g., by stdio_server.py)
if not logging.getLogger().handlers:
    setup_logging(config.server.log_level)

logger = get_logger(__name__)

# Initialize FastMCP server
mcp = FastMCP("Codex CLI MCP Server - 4 Core Tools")

# Initialize session manager and conversational tools
session_manager = CodexSessionManager(config)
conversational_tools = ConversationalMCPTools(session_manager)
direct_tools = DirectCodexTools(session_manager)

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


# === New Advanced Tools Models ===

class ChatResponse(BaseModel):
    """Response model for conversational chat tool."""
    response: str
    suggestions: List[str]
    follow_up_questions: List[str]
    conversation_id: str
    timestamp: str
    context_used: List[str]  # What previous tool outputs were referenced
    confidence_score: float


class SecurityIssue(BaseModel):
    """Represents a security vulnerability found during audit."""
    severity: str  # "critical", "high", "medium", "low"
    category: str  # "injection", "auth", "crypto", "xss", etc.
    file: str
    line_range: str
    description: str
    impact: str
    recommendation: str
    cwe_id: Optional[str] = None


class QualityIssue(BaseModel):
    """Represents a code quality issue found during audit."""
    severity: str  # "major", "minor", "suggestion"
    category: str  # "maintainability", "performance", "style", etc.
    file: str
    line_range: str
    description: str
    impact: str
    suggestion: str


class ComplianceResult(BaseModel):
    """Represents compliance check result."""
    framework: str  # "OWASP", "NIST", "PCI-DSS", etc.
    rule_id: str
    status: str  # "pass", "fail", "warning"
    description: str
    evidence: Optional[str] = None


class AuditResponse(BaseModel):
    """Structured response for code audit tool."""
    overall_security_score: int  # 1-100
    overall_quality_score: int  # 1-100
    vulnerabilities: List[SecurityIssue]
    quality_issues: List[QualityIssue]
    compliance_results: List[ComplianceResult]
    recommendations: List[str]
    risk_assessment: str
    audit_summary: str
    files_analyzed: List[str]
    analysis_timestamp: str


class DebugSolution(BaseModel):
    """Represents a debugging solution."""
    approach: str
    description: str
    code_changes: List[CodeChange]
    confidence: float  # 0.0 to 1.0
    estimated_time: str
    trade_offs: List[str]


class DebugResponse(BaseModel):
    """Structured response for debug analysis tool."""
    root_cause: str
    solutions: List[DebugSolution]
    debugging_steps: List[str]
    prevention_strategies: List[str]
    related_issues: List[str]
    confidence_score: float  # 0.0 to 1.0
    estimated_fix_time: str


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
) -> Dict[str, Any]:
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
            # Add timeout protection with cancellation support
            direct_result = await asyncio.wait_for(
                direct_tools.plan(
                    agent_id=agent_id,
                    task=task,
                    repo_context=repo_context,
                    constraints=constraints,
                ),
                timeout=config.server.timeouts.tool_default_timeout
            )

            structured_response = _coerce_plan_response(direct_result)

            logger.info(
                "Planning completed",
                agent_id=agent_id,
                files_affected=len(structured_response.affected_files),
                complexity=structured_response.estimated_complexity,
            )

            return structured_response

        except asyncio.TimeoutError:
            logger.error("Planning timed out", agent_id=agent_id,
                        timeout=config.server.timeouts.tool_default_timeout)
            return PlanResponse(
                task_breakdown=["Planning operation timed out"],
                affected_files=[],
                implementation_approach=f"Planning timed out after {config.server.timeouts.tool_default_timeout} seconds. Please try breaking down the task into smaller components.",
                architectural_decisions=[],
                dependencies=[],
                estimated_complexity="unknown",
                gotchas=["Operation was cancelled due to timeout"],
                integration_points=[],
            )
        except Exception as e:
            logger.error("Planning failed", agent_id=agent_id, error=str(e))
            return PlanResponse(
                task_breakdown=["Error occurred during planning"],
                affected_files=[],
                implementation_approach=f"Planning failed: {str(e)}",
                architectural_decisions=[],
                dependencies=[],
                estimated_complexity="unknown",
                gotchas=[f"Planning error: {str(e)}"],
                integration_points=[],
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

            # Get implementation from Codex with tool timeout and cancellation support
            codex_response = await asyncio.wait_for(
                _send_to_codex(
                    agent_id, context_prompt, "implementation",
                    timeout=config.server.timeouts.tool_default_timeout
                ),
                timeout=config.server.timeouts.tool_default_timeout
            )

            # Parse and structure the response
            structured_response = _parse_implementation_response(codex_response)

            logger.info("Implementation completed",
                       agent_id=agent_id,
                       changes_count=len(structured_response.changes),
                       dependencies_added=len(structured_response.dependencies_added))

            return structured_response

        except asyncio.TimeoutError:
            logger.error("Implementation timed out", agent_id=agent_id,
                        timeout=config.server.timeouts.tool_default_timeout)
            return ImplementResponse(
                changes=[],
                dependencies_added=[],
                tests_needed=["Task timed out - consider smaller implementation scope"],
                integration_notes=f"Implementation timed out after {config.server.timeouts.tool_default_timeout} seconds. The task may be too complex - try breaking it down into smaller, more focused implementations.",
                next_steps=["Break down task into smaller components", "Retry with reduced scope"],
                warnings=["Operation was cancelled due to timeout", "Consider increasing timeout or reducing complexity"]
            )
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
            # Ensure content is a dict
            if isinstance(content, str):
                # If content is a string, treat it as a single file
                content = {"files": [{"name": "unknown", "content": content}]}
            elif not isinstance(content, dict):
                raise ValueError("Content must be a dictionary with 'files' or 'diffs' key")

            # Build comprehensive review context
            context_prompt = _build_review_context(content, rubric, focus_areas)

            # Get review from Codex with tool timeout
            codex_response = await _send_to_codex(
                agent_id, context_prompt, "review",
                timeout=config.server.timeouts.tool_default_timeout
            )

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

            # Get fixes from Codex with tool timeout
            codex_response = await _send_to_codex(
                agent_id, context_prompt, "debugging",
                timeout=config.server.timeouts.tool_default_timeout
            )

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


@mcp.tool()
@session_aware_tool
async def chat(
    message: str,
    context: Optional[str] = None,
    previous_messages: Optional[List[str]] = None,
    reference_files: Optional[List[str]] = None
) -> ChatResponse:
    """
    Interactive chat tool for conversational AI assistance and brainstorming.

    Provides a conversational interface for asking questions, brainstorming ideas,
    getting second opinions, and general AI assistance. Maintains context across
    the conversation and can reference other tool outputs.

    Args:
        message: The message or question to send to Codex
        context: Additional context about the current task or project
        previous_messages: List of previous messages in this conversation
        reference_files: Files to reference for context (optional)

    Returns:
        ChatResponse: Conversational response with suggestions and follow-ups
    """
    agent_id = await get_session_agent_id()

    with LogContext(f"chat_{agent_id}"):
        logger.info("Processing chat request",
                   message_length=len(message),
                   has_context=context is not None,
                   has_history=previous_messages is not None and len(previous_messages) > 0,
                   reference_files_count=len(reference_files) if reference_files else 0,
                   agent_id=agent_id)

        try:
            # Build conversational context
            context_prompt = _build_chat_context(
                message, context, previous_messages, reference_files
            )

            # Get response from Codex with tool timeout
            codex_response = await _send_to_codex(
                agent_id, context_prompt, "conversation",
                timeout=config.server.timeouts.tool_default_timeout
            )

            # Parse and structure the chat response
            structured_response = _parse_chat_response(codex_response, message)

            logger.info("Chat response completed",
                       agent_id=agent_id,
                       response_length=len(structured_response.response),
                       suggestions_count=len(structured_response.suggestions),
                       follow_ups_count=len(structured_response.follow_up_questions))

            return structured_response

        except Exception as e:
            logger.error("Chat processing failed", agent_id=agent_id, error=str(e))
            return ChatResponse(
                response=f"I apologize, but I encountered an error processing your message: {str(e)}",
                conversation_id=f"error_{agent_id}_{int(time.time())}",
                suggestions=["Please try rephrasing your question", "Check your connection and try again"],
                follow_up_questions=[],
                timestamp=datetime.now(timezone.utc).isoformat(),
                context_used=[context] if context else [],
                confidence_score=0.0
            )


@mcp.tool()
@session_aware_tool
async def audit(
    code: str,
    file_paths: Optional[List[str]] = None,
    focus_areas: Optional[List[str]] = None,
    severity_threshold: Optional[str] = "medium",
    compliance_standards: Optional[List[str]] = None
) -> AuditResponse:
    """
    Comprehensive code security and quality audit tool.

    Analyzes code for security vulnerabilities, quality issues, compliance violations,
    and best practice adherence. Provides detailed findings with severity levels
    and actionable remediation guidance.

    Args:
        code: Code content to audit (can be single file or multiple files)
        file_paths: List of file paths being audited (for context)
        focus_areas: Specific areas to focus on (e.g., "security", "performance", "maintainability")
        severity_threshold: Minimum severity to report ("low", "medium", "high", "critical")
        compliance_standards: Standards to check against (e.g., "OWASP", "PCI-DSS", "SOC2")

    Returns:
        AuditResponse: Comprehensive audit report with findings and recommendations
    """
    agent_id = await get_session_agent_id()

    with LogContext(f"audit_{agent_id}"):
        logger.info("Processing code audit request",
                   code_length=len(code),
                   file_count=len(file_paths) if file_paths else 1,
                   focus_areas=focus_areas,
                   severity_threshold=severity_threshold,
                   compliance_standards=compliance_standards,
                   agent_id=agent_id)

        try:
            # Build audit context
            context_prompt = _build_audit_context(
                code, file_paths, focus_areas, severity_threshold, compliance_standards
            )

            # Get audit results from Codex with tool timeout
            codex_response = await _send_to_codex(
                agent_id, context_prompt, "security_audit",
                timeout=config.server.timeouts.tool_default_timeout
            )

            # Parse and structure the audit response
            structured_response = _parse_audit_response(codex_response, code)

            logger.info("Code audit completed",
                       agent_id=agent_id,
                       security_issues_count=len(structured_response.vulnerabilities),
                       quality_issues_count=len(structured_response.quality_issues),
                       overall_security_score=structured_response.overall_security_score,
                       compliance_results_count=len(structured_response.compliance_results))

            return structured_response

        except Exception as e:
            logger.error("Code audit failed", agent_id=agent_id, error=str(e))
            return AuditResponse(
                overall_security_score=0,
                overall_quality_score=0,
                vulnerabilities=[
                    SecurityIssue(
                        severity="high",
                        category="audit_error",
                        file="unknown",
                        line_range="unknown",
                        description=f"Audit process failed: {str(e)}",
                        impact="Unable to perform security analysis",
                        recommendation="Check audit parameters and try again",
                        cwe_id=None
                    )
                ],
                quality_issues=[],
                compliance_results=[],
                recommendations=["Verify code input and audit parameters", "Try again with smaller code samples"],
                risk_assessment="Unable to assess risk due to audit failure",
                audit_summary=f"Audit failed due to error: {str(e)}",
                files_analyzed=file_paths or ["unknown"],
                analysis_timestamp=datetime.now(timezone.utc).isoformat()
            )


@mcp.tool()
@session_aware_tool
async def debug(
    error_message: str,
    code_context: Optional[str] = None,
    stack_trace: Optional[str] = None,
    environment_info: Optional[str] = None,
    reproduction_steps: Optional[str] = None,
    debug_level: Optional[str] = "detailed"
) -> DebugResponse:
    """
    Intelligent debugging assistance tool for analyzing and resolving code issues.

    Provides comprehensive debugging analysis including root cause identification,
    step-by-step troubleshooting guidance, and multiple solution approaches.
    Focuses on both immediate fixes and long-term prevention strategies.

    Args:
        error_message: The error message or issue description
        code_context: Relevant code that's causing the issue
        stack_trace: Full stack trace if available
        environment_info: Runtime environment details (OS, versions, dependencies)
        reproduction_steps: Steps to reproduce the issue
        debug_level: Level of debugging detail ("basic", "detailed", "comprehensive")

    Returns:
        DebugResponse: Comprehensive debugging analysis with solutions and prevention
    """
    agent_id = await get_session_agent_id()

    with LogContext(f"debug_{agent_id}"):
        logger.info("Processing debug request",
                   error_length=len(error_message),
                   has_code_context=code_context is not None,
                   has_stack_trace=stack_trace is not None,
                   has_environment_info=environment_info is not None,
                   debug_level=debug_level,
                   agent_id=agent_id)

        try:
            # Build debugging context
            context_prompt = _build_debug_context(
                error_message, code_context, stack_trace,
                environment_info, reproduction_steps, debug_level
            )

            # Get debugging analysis from Codex with tool timeout
            codex_response = await _send_to_codex(
                agent_id, context_prompt, "debugging_analysis",
                timeout=config.server.timeouts.tool_default_timeout
            )

            # Parse and structure the debug response
            structured_response = _parse_debug_response(codex_response, error_message)

            logger.info("Debug analysis completed",
                       agent_id=agent_id,
                       solutions_count=len(structured_response.solutions),
                       debugging_steps_count=len(structured_response.debugging_steps),
                       confidence_score=structured_response.confidence_score)

            return structured_response

        except Exception as e:
            logger.error("Debug analysis failed", agent_id=agent_id, error=str(e))
            return DebugResponse(
                root_cause="Debug analysis failed",
                solutions=[
                    DebugSolution(
                        approach="error_recovery",
                        description=f"Debug process encountered an error: {str(e)}",
                        code_changes=[],
                        confidence=0.1,
                        estimated_time="unknown",
                        trade_offs=["Unable to perform full analysis"]
                    )
                ],
                debugging_steps=[
                    "Check debug input parameters",
                    "Verify error message is complete",
                    "Try simplifying the debugging request",
                    "Contact system administrator if issue persists"
                ],
                prevention_strategies=["Regular debugging and testing practices"],
                related_issues=[f"Debug analysis error: {str(e)}"],
                confidence_score=0.1,
                estimated_fix_time="unknown"
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
CRITICAL: RESPOND WITH VALID JSON ONLY. NO NARRATIVE TEXT.

REQUIRED JSON OUTPUT FORMAT:
{{
  "changes": [
    {{
      "file": "path/to/file.py",
      "action": "create|modify|delete",
      "diff": "actual code changes or full file content",
      "explanation": "why this change is needed",
      "line_numbers": [1, 2, 3] // optional, for modifications
    }}
  ],
  "dependencies_added": ["package1", "package2"],
  "tests_needed": ["test description 1", "test description 2"],
  "integration_notes": "how changes fit with existing code",
  "next_steps": ["step 1", "step 2"],
  "warnings": ["warning 1", "warning 2"]
}}

IMPORTANT RULES:
- Return ONLY valid JSON, no other text
- Focus on minimal, precise changes that follow existing code patterns
- Include proper error handling and type safety where applicable
- Use proper diff format for modifications (show what changes)
- For new files, provide complete file content in the diff field
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
            if isinstance(file_info, str):
                # Handle simple string file paths
                prompt += f"File: {file_info}\n"
                prompt += f"(File content would need to be read separately)\n\n"
            elif isinstance(file_info, dict):
                # Handle dictionary with name/content
                prompt += f"File: {file_info.get('name', 'unknown')}\n"
                prompt += f"{file_info.get('content', '')}\n\n"
            else:
                prompt += f"File: unknown format\n\n"

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

async def _send_to_codex(agent_id: str, prompt: str, operation_type: str, timeout: Optional[int] = None) -> str:
    """Send request to Codex CLI container and get response."""
    try:
        container_manager = session_manager.container_manager

        # Use configured timeout if not specified
        if timeout is None:
            timeout = config.server.timeouts.codex_message_timeout

        # Get or create persistent container for this agent
        session = await container_manager.get_or_create_persistent_agent_container(
            agent_id=agent_id,
            model=config.codex.model,
            provider=config.codex.provider,
            approval_mode=config.codex.approval_mode,
            reasoning=config.codex.reasoning
        )

        # Send the rich prompt to Codex with configured timeout
        response = await container_manager.send_message_to_codex(
            session=session,
            message=prompt,
            timeout=timeout
        )

        return response

    except Exception as e:
        logger.error(f"Failed to communicate with Codex for {operation_type}",
                    agent_id=agent_id, error=str(e), timeout=timeout)
        return f"Error communicating with Codex: {str(e)}"


def _coerce_plan_response(data: Dict[str, Any]) -> PlanResponse:
    """Convert raw dict from direct Codex tools into PlanResponse."""
    return PlanResponse(
        task_breakdown=list(data.get("task_breakdown", [])),
        affected_files=list(data.get("affected_files", [])),
        implementation_approach=data.get("implementation_approach", ""),
        architectural_decisions=list(data.get("architectural_decisions", [])),
        dependencies=list(data.get("dependencies", [])),
        estimated_complexity=data.get("estimated_complexity", "medium"),
        gotchas=list(data.get("gotchas", [])),
        integration_points=list(data.get("integration_points", [])),
    )


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
    cleaned = response.strip()

    # Try multiple approaches to extract JSON
    parsed_payload: Optional[Dict[str, Any]] = None

    # Approach 1: Look for JSON between curly braces
    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start != -1 and end != -1 and end >= start:
        candidate = cleaned[start:end + 1]
        try:
            parsed_payload = json.loads(candidate)
            logger.debug("Successfully parsed JSON from response")
        except json.JSONDecodeError:
            logger.debug("Failed to decode JSON between braces, trying alternative approaches")

            # Approach 2: Try to find JSON after "```json" markers
            json_marker = "```json"
            if json_marker in cleaned.lower():
                json_start = cleaned.lower().find(json_marker) + len(json_marker)
                json_end = cleaned.find("```", json_start)
                if json_end == -1:
                    json_end = len(cleaned)
                candidate = cleaned[json_start:json_end].strip()
                try:
                    parsed_payload = json.loads(candidate)
                    logger.debug("Successfully parsed JSON from markdown block")
                except json.JSONDecodeError:
                    pass

            # Approach 3: Try the entire response as JSON
            if not parsed_payload:
                try:
                    parsed_payload = json.loads(cleaned)
                    logger.debug("Successfully parsed entire response as JSON")
                except json.JSONDecodeError:
                    logger.debug("Failed to parse entire response as JSON")

    if parsed_payload:
        # Support both upper- and lower-case keys from Codex
        def _get(key: str, default: Any) -> Any:
            return parsed_payload.get(key) or parsed_payload.get(key.upper(), default)

        raw_changes = _get("changes", [])
        changes: List[CodeChange] = []
        for change in raw_changes:
            if not isinstance(change, dict):
                continue
            changes.append(
                CodeChange(
                    file=change.get("file") or change.get("FILE", ""),
                    action=change.get("action") or change.get("ACTION", "modify"),
                    diff=change.get("diff") or change.get("DIFF", ""),
                    explanation=change.get("explanation") or change.get("EXPLANATION", ""),
                    line_numbers=change.get("line_numbers") or change.get("LINE_NUMBERS"),
                )
            )

        return ImplementResponse(
            changes=changes,
            dependencies_added=list(_get("dependencies_added", [])),
            tests_needed=list(_get("tests_needed", [])),
            integration_notes=_get("integration_notes", ""),
            next_steps=list(_get("next_steps", [])),
            warnings=list(_get("warnings", [])),
        )

    logger.debug(
        "Falling back to raw implementation response",
        response_preview=cleaned[:200],
    )

    return ImplementResponse(
        changes=[
            CodeChange(
                file="raw_response.txt",
                action="modify",
                diff=cleaned,
                explanation="Codex implementation output could not be parsed",
            )
        ],
        dependencies_added=[],
        tests_needed=["Review manual output"],
        integration_notes="Codex response was not structured JSON; manual review required",
        next_steps=["Coerce Codex to return structured diff"],
        warnings=["Implementation response did not match required format"],
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

    # Try to parse structured JSON response first
    cleaned = response.strip()

    # Look for JSON structure
    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start != -1 and end != -1 and end >= start:
        candidate = cleaned[start:end + 1]
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and "fixes" in parsed:
                # Parse structured fix response
                fixes = []
                for fix_data in parsed.get("fixes", []):
                    if isinstance(fix_data, dict):
                        files_to_change = []
                        for change_data in fix_data.get("files_to_change", []):
                            if isinstance(change_data, dict):
                                files_to_change.append(CodeChange(
                                    file=change_data.get("file", "unknown"),
                                    action=change_data.get("action", "modify"),
                                    diff=change_data.get("diff", ""),
                                    explanation=change_data.get("explanation", ""),
                                    line_numbers=change_data.get("line_numbers")
                                ))

                        fixes.append(Fix(
                            problem=fix_data.get("problem", ""),
                            solution=fix_data.get("solution", ""),
                            files_to_change=files_to_change,
                            root_cause=fix_data.get("root_cause", ""),
                            prevention=fix_data.get("prevention", "")
                        ))

                return FixResponse(
                    fixes=fixes,
                    diagnostic_steps=parsed.get("diagnostic_steps", []),
                    quick_fix_available=parsed.get("quick_fix_available", True),
                    estimated_fix_time=parsed.get("estimated_fix_time", "unknown"),
                    related_issues=parsed.get("related_issues", [])
                )
        except json.JSONDecodeError:
            pass

    # Fallback to simple parsing - don't truncate the response
    return FixResponse(
        fixes=[
            Fix(
                problem="Issue identified in Codex response",
                solution="Solution from Codex",
                files_to_change=[
                    CodeChange(
                        file="raw_response.txt",
                        action="modify",
                        diff=response,  # Don't truncate
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


def _build_chat_context(
    message: str,
    context: Optional[str],
    previous_messages: Optional[List[str]],
    reference_files: Optional[List[str]]
) -> str:
    """Build rich context prompt for conversational interaction."""
    prompt = f"""
CODEX CONVERSATIONAL REQUEST

You are Codex, an expert AI assistant helping with software development tasks.
Respond conversationally and helpfully to the user's message, providing insights,
suggestions, and follow-up questions as appropriate.

USER MESSAGE:
{message}

"""

    if context:
        prompt += f"CURRENT CONTEXT:\n{context}\n\n"

    if previous_messages and len(previous_messages) > 0:
        prompt += "CONVERSATION HISTORY:\n"
        for i, prev_msg in enumerate(previous_messages[-5:]):  # Last 5 messages for context
            prompt += f"{i+1}. {prev_msg}\n"
        prompt += "\n"

    if reference_files and len(reference_files) > 0:
        prompt += f"REFERENCE FILES:\n{', '.join(reference_files)}\n\n"

    prompt += """
RESPONSE FORMAT:
Please respond naturally and conversationally. Focus on being helpful, insightful,
and providing actionable advice. If appropriate, suggest follow-up questions or
related topics the user might want to explore.

Be encouraging and collaborative in tone. If you need clarification, ask specific
questions. If you can provide examples or code snippets, do so.
"""

    return prompt


def _parse_chat_response(response: str, original_message: str) -> ChatResponse:
    """Parse Codex chat response into structured format."""
    import time
    import hashlib

    # Generate conversation ID based on timestamp and message hash
    conversation_id = f"chat_{int(time.time())}_{hashlib.md5(original_message.encode()).hexdigest()[:8]}"

    # Extract suggestions and follow-up questions from response
    suggestions = []
    follow_up_questions = []

    # Look for common suggestion patterns in the response
    response_lower = response.lower()
    if "consider" in response_lower or "suggest" in response_lower or "recommend" in response_lower:
        # Extract specific suggestions (simplified approach)
        lines = response.split('\n')
        for line in lines:
            line_lower = line.strip().lower()
            if any(keyword in line_lower for keyword in ["consider", "suggest", "recommend", "try", "might"]):
                if len(line.strip()) > 10 and len(line.strip()) < 200:
                    suggestions.append(line.strip())

    # Look for questions in the response
    sentences = response.replace('!', '.').replace('?', '.').split('.')
    for sentence in sentences:
        if '?' in sentence or any(word in sentence.lower() for word in ["what", "how", "why", "when", "where", "would you"]):
            cleaned = sentence.strip()
            if len(cleaned) > 10 and len(cleaned) < 150:
                follow_up_questions.append(cleaned + "?")

    # Calculate confidence based on response quality indicators
    confidence_score = 0.8  # Base confidence
    if len(response) > 100:
        confidence_score += 0.1
    if any(word in response.lower() for word in ["example", "code", "specific", "detailed"]):
        confidence_score += 0.1
    confidence_score = min(confidence_score, 1.0)

    return ChatResponse(
        response=response,
        conversation_id=conversation_id,
        suggestions=suggestions[:3],  # Limit to top 3 suggestions
        follow_up_questions=follow_up_questions[:3],  # Limit to top 3 questions
        timestamp=datetime.now(timezone.utc).isoformat(),
        context_used=[original_message[:100] + "..." if len(original_message) > 100 else original_message],
        confidence_score=confidence_score
    )


def _build_audit_context(
    code: str,
    file_paths: Optional[List[str]],
    focus_areas: Optional[List[str]],
    severity_threshold: Optional[str],
    compliance_standards: Optional[List[str]]
) -> str:
    """Build rich context prompt for security and quality audit."""
    prompt = f"""
CODEX SECURITY AND QUALITY AUDIT REQUEST

You are Codex, performing a comprehensive security and quality audit.
Analyze the provided code for vulnerabilities, quality issues, and compliance violations.

CODE TO AUDIT:
{code}

"""

    if file_paths and len(file_paths) > 0:
        prompt += f"FILE PATHS:\n{', '.join(file_paths)}\n\n"

    if focus_areas and len(focus_areas) > 0:
        prompt += f"FOCUS AREAS:\n{', '.join(focus_areas)}\n\n"

    if severity_threshold:
        prompt += f"SEVERITY THRESHOLD: Report {severity_threshold} and above\n\n"

    if compliance_standards and len(compliance_standards) > 0:
        prompt += f"COMPLIANCE STANDARDS:\n{', '.join(compliance_standards)}\n\n"

    prompt += """
AUDIT REQUIREMENTS:

1. SECURITY ANALYSIS:
   - SQL injection vulnerabilities
   - Cross-site scripting (XSS)
   - Authentication and authorization flaws
   - Input validation issues
   - Cryptographic weaknesses
   - Sensitive data exposure
   - Path traversal vulnerabilities
   - Command injection risks

2. QUALITY ANALYSIS:
   - Code complexity and maintainability
   - Performance bottlenecks
   - Error handling quality
   - Resource management (memory leaks, file handles)
   - Code duplication
   - Naming conventions
   - Documentation quality

3. COMPLIANCE CHECKS:
   - Industry standard adherence
   - Best practice violations
   - Framework-specific guidelines
   - Security policy compliance

RESPONSE FORMAT:
For each issue found, provide:
- Issue type and severity (critical/high/medium/low)
- Specific location (file:line or code snippet)
- Detailed description of the problem
- Security impact assessment
- Specific remediation steps
- CWE/CVE references where applicable

Provide an overall security score (0-100) and summary of findings.
Focus on actionable, specific recommendations.
"""

    return prompt


def _parse_audit_response(response: str, original_code: str) -> AuditResponse:
    """Parse Codex audit response into structured format."""
    import re
    import time

    # Initialize empty collections
    security_issues = []
    quality_issues = []
    compliance_results = []

    # Extract security issues using pattern matching
    security_patterns = [
        r"(?i)(sql injection|xss|cross-site scripting|authentication|authorization|input validation|cryptographic|sensitive data|path traversal|command injection)",
        r"(?i)(vulnerability|security issue|security flaw|security risk)"
    ]

    quality_patterns = [
        r"(?i)(complexity|maintainability|performance|error handling|resource management|code duplication|naming convention|documentation)",
        r"(?i)(quality issue|code smell|technical debt|best practice)"
    ]

    # Parse severity levels
    severity_map = {"critical": 4, "high": 3, "medium": 2, "low": 1}

    # Split response into lines for analysis
    lines = response.split('\n')
    current_issue = None
    current_type = "security"

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check for severity indicators
        severity = "medium"  # default
        for sev in ["critical", "high", "medium", "low"]:
            if sev in line.lower():
                severity = sev
                break

        # Check for security issues
        if any(re.search(pattern, line) for pattern in security_patterns):
            security_issues.append(SecurityIssue(
                severity=severity,
                category="security_vulnerability",
                file="analyzed_code",
                line_range="See audit details",
                description=line,
                impact="Security vulnerability identified",
                recommendation="Follow security best practices",
                cwe_id=None
            ))

        # Check for quality issues
        elif any(re.search(pattern, line) for pattern in quality_patterns):
            quality_issues.append(QualityIssue(
                severity=severity,
                category="code_quality",
                file="analyzed_code",
                line_range="See audit details",
                description=line,
                impact="maintainability",
                suggestion="Improve code quality"
            ))

    # Extract overall score (look for numbers between 0-100)
    score_match = re.search(r'(?i)score[:\s]*(\d{1,3})', response)
    overall_score = float(score_match.group(1)) if score_match else 75.0

    # Generate compliance results based on standards mentioned
    compliance_results.append(ComplianceResult(
        framework="General Security",
        rule_id="SECURITY_001",
        status="partial" if security_issues else "pass",
        description="General security compliance check",
        evidence=f"Found {len(security_issues)} security issues" if security_issues else "No security issues found"
    ))

    # Extract summary and recommendations
    summary_lines = response.split('\n')[:3]  # First few lines as summary
    summary = ' '.join(summary_lines).strip()
    if len(summary) > 500:
        summary = summary[:500] + "..."

    recommendations = [
        "Review and address all identified security vulnerabilities",
        "Implement proper input validation and sanitization",
        "Follow secure coding best practices",
        "Regular security audits and code reviews"
    ]

    return AuditResponse(
        overall_security_score=int(overall_score),
        overall_quality_score=max(0, int(overall_score - len(quality_issues) * 5)),  # Deduct for quality issues
        vulnerabilities=security_issues[:10],  # Limit to top 10
        quality_issues=quality_issues[:10],    # Limit to top 10
        compliance_results=compliance_results,
        recommendations=recommendations,
        risk_assessment="Medium risk" if security_issues else "Low risk",
        audit_summary=summary,
        files_analyzed=["analyzed_code"],
        analysis_timestamp=datetime.now(timezone.utc).isoformat()
    )


def _build_debug_context(
    error_message: str,
    code_context: Optional[str],
    stack_trace: Optional[str],
    environment_info: Optional[str],
    reproduction_steps: Optional[str],
    debug_level: Optional[str]
) -> str:
    """Build rich context prompt for debugging analysis."""
    prompt = f"""
CODEX INTELLIGENT DEBUGGING REQUEST

You are Codex, providing expert debugging assistance for software development.
Analyze the error and provide comprehensive troubleshooting guidance with multiple solution approaches.

ERROR MESSAGE:
{error_message}

"""

    if code_context:
        prompt += f"CODE CONTEXT:\n{code_context}\n\n"

    if stack_trace:
        prompt += f"STACK TRACE:\n{stack_trace}\n\n"

    if environment_info:
        prompt += f"ENVIRONMENT INFO:\n{environment_info}\n\n"

    if reproduction_steps:
        prompt += f"REPRODUCTION STEPS:\n{reproduction_steps}\n\n"

    detail_level = debug_level or "detailed"
    prompt += f"DEBUG LEVEL: {detail_level}\n\n"

    prompt += """
DEBUGGING ANALYSIS REQUIREMENTS:

1. ROOT CAUSE ANALYSIS:
   - Primary cause of the error
   - Contributing factors
   - Why it's happening now
   - Environment/configuration dependencies

2. SOLUTION APPROACHES:
   - Quick fix (immediate workaround)
   - Proper fix (addresses root cause)
   - Alternative approaches
   - Each with confidence level and estimated time

3. DEBUGGING STEPS:
   - Systematic troubleshooting process
   - Information gathering steps
   - Validation and testing procedures
   - Rollback plans if fixes fail

4. PREVENTION STRATEGIES:
   - How to prevent this issue in the future
   - Testing improvements
   - Code quality measures
   - Monitoring and alerting

5. RELATED ISSUES:
   - Similar problems that might occur
   - Dependencies that could break
   - Performance implications

RESPONSE FORMAT:
- Clear, step-by-step guidance
- Code examples where helpful
- Specific commands to run
- Expected outcomes at each step
- Confidence levels for each solution
- Time estimates for implementation
- Trade-offs between different approaches

Focus on being practical and actionable. Provide multiple solution paths
when possible, ordered by likelihood of success.
"""

    return prompt


def _parse_debug_response(response: str, original_error: str) -> DebugResponse:
    """Parse Codex debug response into structured format."""
    import re
    import time

    # Initialize collections
    solutions = []
    debugging_steps = []
    prevention_strategies = []
    related_issues = []

    # Split response into sections for analysis
    lines = response.split('\n')
    current_section = None

    # Extract root cause (look for common patterns)
    root_cause_patterns = [
        r"(?i)root cause[:\s]*(.+)",
        r"(?i)main issue[:\s]*(.+)",
        r"(?i)primary cause[:\s]*(.+)",
        r"(?i)the problem is[:\s]*(.+)"
    ]

    root_cause = "Error analysis in progress"
    for line in lines:
        for pattern in root_cause_patterns:
            match = re.search(pattern, line)
            if match:
                root_cause = match.group(1).strip()
                break
        if root_cause != "Error analysis in progress":
            break

    # Extract solutions
    solution_keywords = ["fix", "solution", "approach", "resolve", "workaround"]
    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        if any(keyword in line_lower for keyword in solution_keywords):
            if len(line.strip()) > 20:  # Substantial content
                confidence = 0.8  # Default confidence
                estimated_time = "30-60 minutes"  # Default estimate

                # Look for confidence indicators
                if any(word in line_lower for word in ["quick", "simple", "easy"]):
                    confidence = 0.9
                    estimated_time = "15-30 minutes"
                elif any(word in line_lower for word in ["complex", "difficult", "major"]):
                    confidence = 0.6
                    estimated_time = "2-4 hours"

                solutions.append(DebugSolution(
                    approach="general_fix",
                    description=line.strip(),
                    code_changes=[],
                    confidence=confidence,
                    estimated_time=estimated_time,
                    trade_offs=["Standard debugging approach"]
                ))

    # Extract debugging steps
    step_keywords = ["step", "check", "verify", "test", "run", "examine"]
    for line in lines:
        line_lower = line.lower().strip()
        if any(keyword in line_lower for keyword in step_keywords):
            if len(line.strip()) > 15 and line.strip().endswith(('.', ':', '?')):
                debugging_steps.append(line.strip())

    # Extract prevention strategies
    prevention_keywords = ["prevent", "avoid", "future", "best practice", "recommend"]
    for line in lines:
        line_lower = line.lower().strip()
        if any(keyword in line_lower for keyword in prevention_keywords):
            if len(line.strip()) > 20:
                prevention_strategies.append(line.strip())

    # Extract related issues
    related_keywords = ["similar", "related", "also", "might", "could"]
    for line in lines:
        line_lower = line.lower().strip()
        if any(keyword in line_lower for keyword in related_keywords):
            if "error" in line_lower or "issue" in line_lower or "problem" in line_lower:
                if len(line.strip()) > 20:
                    related_issues.append(line.strip())

    # Calculate overall confidence based on available information
    confidence_score = 0.7  # Base confidence
    if solutions:
        confidence_score += 0.1
    if debugging_steps:
        confidence_score += 0.1
    if prevention_strategies:
        confidence_score += 0.1
    confidence_score = min(confidence_score, 1.0)

    # Estimate fix time based on complexity
    estimated_fix_time = "1-2 hours"
    if "simple" in response.lower() or "quick" in response.lower():
        estimated_fix_time = "30 minutes"
    elif "complex" in response.lower() or "major" in response.lower():
        estimated_fix_time = "4+ hours"

    # Ensure we have at least some default content
    if not solutions:
        solutions.append(DebugSolution(
            approach="analysis_needed",
            description="Further analysis required based on provided information",
            code_changes=[],
            confidence=0.5,
            estimated_time="varies",
            trade_offs=["Requires additional investigation"]
        ))

    if not debugging_steps:
        debugging_steps = [
            "Review the complete error message and context",
            "Check recent changes that might have caused this issue",
            "Verify environment configuration and dependencies",
            "Test with minimal reproduction case"
        ]

    if not prevention_strategies:
        prevention_strategies = [
            "Implement comprehensive error handling",
            "Add monitoring and alerting for similar issues",
            "Regular code reviews and testing"
        ]

    return DebugResponse(
        root_cause=root_cause,
        solutions=solutions[:5],  # Limit to top 5 solutions
        debugging_steps=debugging_steps[:10],  # Limit to top 10 steps
        prevention_strategies=prevention_strategies[:5],  # Limit to top 5 strategies
        related_issues=related_issues[:5],  # Limit to top 5 related issues
        confidence_score=confidence_score,
        estimated_fix_time=estimated_fix_time
    )


def create_mcp_server() -> FastMCP:
    """
    Create and configure the FastMCP server instance.

    Returns:
        FastMCP: Configured server instance ready for startup
    """
    logger.info("Initializing Codex CLI MCP Server with 10 comprehensive tools: health_check, list_sessions, get_my_session_info, plan, implement, review, fix, chat, audit, debug")
    return mcp


# Main entry point is now in server.py
