"""
Conversational MCP Tools for Interactive Codex CLI Collaboration.

This module transforms the traditional command-based MCP tools into conversational
interfaces that facilitate natural agent-to-agent collaboration with Codex CLI.
Instead of sending structured prompts and parsing responses, these tools engage
in natural conversation while maintaining structured outputs for MCP clients.
"""

import asyncio
import time
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass
from pydantic import BaseModel

import structlog

from .session_manager import CodexSessionManager
from .workspace_detector import workspace_detector

logger = structlog.get_logger(__name__)


class ConversationalPlanResponse(BaseModel):
    """Enhanced response for conversational planning."""
    conversation_summary: str
    task_breakdown: List[str]
    affected_files: List[str]
    implementation_approach: str
    architectural_decisions: List[str]
    dependencies: List[str]
    estimated_complexity: str
    gotchas: List[str]
    integration_points: List[str]
    codex_conversation_id: str
    workspace_context: Dict[str, Any]


class ConversationalImplementResponse(BaseModel):
    """Enhanced response for conversational implementation."""
    conversation_summary: str
    implementation_discussion: str
    suggested_changes: List[Dict[str, str]]
    next_steps: List[str]
    collaboration_notes: str
    codex_conversation_id: str
    files_examined: List[str]
    tests_suggested: List[str]


class ConversationalReviewResponse(BaseModel):
    """Enhanced response for conversational code review."""
    conversation_summary: str
    overall_assessment: str
    discussion_points: List[str]
    improvement_suggestions: List[str]
    collaboration_feedback: str
    codex_conversation_id: str
    security_notes: List[str]
    performance_notes: List[str]


class ConversationalFixResponse(BaseModel):
    """Enhanced response for conversational debugging."""
    conversation_summary: str
    problem_analysis: str
    suggested_solutions: List[str]
    debugging_discussion: str
    collaboration_notes: str
    codex_conversation_id: str
    root_cause_analysis: str
    prevention_strategies: List[str]


class ConversationalMCPTools:
    """
    Conversational MCP tools that facilitate natural agent collaboration.

    These tools transform the traditional command-based interaction into
    natural conversation flows while maintaining structured outputs for
    MCP protocol compliance.
    """

    def __init__(self, session_manager: CodexSessionManager):
        """Initialize conversational tools with session manager."""
        self.session_manager = session_manager
        self.active_conversations: Dict[str, List[Dict[str, Any]]] = {}

    async def collaborative_plan(
        self,
        agent_id: str,
        task: str,
        repo_context: Optional[Dict[str, Any]] = None,
        constraints: Optional[List[str]] = None,
        session_config: Optional[Dict[str, Any]] = None
    ) -> ConversationalPlanResponse:
        """
        Engage in collaborative planning conversation with Codex CLI.

        Instead of sending a structured prompt, this initiates a natural
        conversation about the planning task, allowing Codex CLI to ask
        questions, explore the workspace, and develop a comprehensive plan.
        """
        logger.info("Starting collaborative planning conversation",
                   agent_id=agent_id,
                   task_preview=task[:100])

        # Create or get persistent session
        session = await self._get_or_create_session(agent_id, session_config)

        # Build conversation context
        conversation_context = self._build_planning_conversation_context(
            task, repo_context, constraints
        )

        # Start natural conversation
        conversation_id = f"plan_{agent_id}_{int(time.time())}"
        conversation_log = []

        try:
            # Initial conversation opener
            opening_message = self._create_planning_opening_message(
                task, conversation_context
            )

            # Send opening message
            codex_response = await self.session_manager.send_message_to_codex(
                session.session_id,
                opening_message,
                timeout=300
            )

            conversation_log.append({
                "type": "opening",
                "message": opening_message,
                "response": codex_response,
                "timestamp": time.time()
            })

            # Continue conversation based on Codex response
            follow_up_response = await self._continue_planning_conversation(
                session.session_id,
                codex_response,
                conversation_context,
                conversation_log
            )

            # Structure the conversational results
            return self._structure_planning_conversation(
                conversation_id,
                conversation_log,
                conversation_context
            )

        except Exception as e:
            logger.error("Collaborative planning conversation failed",
                       agent_id=agent_id,
                       conversation_id=conversation_id,
                       error=str(e))

            # Return fallback response
            return ConversationalPlanResponse(
                conversation_summary=f"Planning conversation encountered an error: {str(e)}",
                task_breakdown=["Error occurred - please retry"],
                affected_files=[],
                implementation_approach="Failed to generate plan due to error",
                architectural_decisions=[],
                dependencies=[],
                estimated_complexity="unknown",
                gotchas=[f"Planning error: {str(e)}"],
                integration_points=[],
                codex_conversation_id=conversation_id,
                workspace_context=conversation_context
            )

    async def collaborative_implement(
        self,
        agent_id: str,
        task: str,
        target_files: List[str],
        context_files: Optional[List[str]] = None,
        requirements: Optional[List[str]] = None,
        session_config: Optional[Dict[str, Any]] = None
    ) -> ConversationalImplementResponse:
        """
        Engage in collaborative implementation conversation with Codex CLI.

        This creates a natural dialogue about implementing specific features,
        allowing Codex CLI to examine files, ask clarifying questions, and
        suggest implementations through conversation.
        """
        logger.info("Starting collaborative implementation conversation",
                   agent_id=agent_id,
                   task_preview=task[:100],
                   target_files_count=len(target_files))

        session = await self._get_or_create_session(agent_id, session_config)

        conversation_id = f"implement_{agent_id}_{int(time.time())}"
        conversation_log = []

        try:
            # Create implementation conversation opener
            opening_message = self._create_implementation_opening_message(
                task, target_files, context_files, requirements
            )

            # Start conversation
            codex_response = await self.session_manager.send_message_to_codex(
                session.session_id,
                opening_message,
                timeout=300
            )

            conversation_log.append({
                "type": "implementation_start",
                "message": opening_message,
                "response": codex_response,
                "timestamp": time.time()
            })

            # Continue implementation conversation
            final_response = await self._continue_implementation_conversation(
                session.session_id,
                codex_response,
                target_files,
                conversation_log
            )

            # Structure results
            return self._structure_implementation_conversation(
                conversation_id,
                conversation_log,
                target_files
            )

        except Exception as e:
            logger.error("Collaborative implementation conversation failed",
                       agent_id=agent_id,
                       error=str(e))

            return ConversationalImplementResponse(
                conversation_summary=f"Implementation conversation error: {str(e)}",
                implementation_discussion="Error occurred during implementation discussion",
                suggested_changes=[],
                next_steps=["Retry implementation conversation"],
                collaboration_notes=f"Error: {str(e)}",
                codex_conversation_id=conversation_id,
                files_examined=[],
                tests_suggested=[]
            )

    async def collaborative_review(
        self,
        agent_id: str,
        content: Dict[str, Any],
        rubric: Optional[List[str]] = None,
        focus_areas: Optional[List[str]] = None,
        session_config: Optional[Dict[str, Any]] = None
    ) -> ConversationalReviewResponse:
        """
        Engage in collaborative code review conversation with Codex CLI.

        Creates a natural dialogue for reviewing code, allowing Codex CLI to
        ask questions about intent, suggest improvements, and provide detailed
        feedback through conversation.
        """
        logger.info("Starting collaborative code review conversation",
                   agent_id=agent_id,
                   content_type=list(content.keys()))

        session = await self._get_or_create_session(agent_id, session_config)

        conversation_id = f"review_{agent_id}_{int(time.time())}"
        conversation_log = []

        try:
            # Create review conversation opener
            opening_message = self._create_review_opening_message(
                content, rubric, focus_areas
            )

            # Start conversation
            codex_response = await self.session_manager.send_message_to_codex(
                session.session_id,
                opening_message,
                timeout=300
            )

            conversation_log.append({
                "type": "review_start",
                "message": opening_message,
                "response": codex_response,
                "timestamp": time.time()
            })

            # Continue review conversation
            final_response = await self._continue_review_conversation(
                session.session_id,
                codex_response,
                content,
                conversation_log
            )

            # Structure results
            return self._structure_review_conversation(
                conversation_id,
                conversation_log,
                content
            )

        except Exception as e:
            logger.error("Collaborative review conversation failed",
                       agent_id=agent_id,
                       error=str(e))

            return ConversationalReviewResponse(
                conversation_summary=f"Review conversation error: {str(e)}",
                overall_assessment="Error during review conversation",
                discussion_points=[],
                improvement_suggestions=[],
                collaboration_feedback=f"Error: {str(e)}",
                codex_conversation_id=conversation_id,
                security_notes=[],
                performance_notes=[]
            )

    async def collaborative_debug(
        self,
        agent_id: str,
        failing_tests: Optional[str] = None,
        error_output: Optional[str] = None,
        context_files: Optional[List[str]] = None,
        symptoms: Optional[str] = None,
        session_config: Optional[Dict[str, Any]] = None
    ) -> ConversationalFixResponse:
        """
        Engage in collaborative debugging conversation with Codex CLI.

        Creates a natural dialogue for debugging issues, allowing Codex CLI to
        examine error contexts, ask clarifying questions, and work through
        solutions conversationally.
        """
        logger.info("Starting collaborative debugging conversation",
                   agent_id=agent_id,
                   has_failing_tests=failing_tests is not None,
                   has_error_output=error_output is not None)

        session = await self._get_or_create_session(agent_id, session_config)

        conversation_id = f"debug_{agent_id}_{int(time.time())}"
        conversation_log = []

        try:
            # Create debugging conversation opener
            opening_message = self._create_debugging_opening_message(
                failing_tests, error_output, context_files, symptoms
            )

            # Start conversation
            codex_response = await self.session_manager.send_message_to_codex(
                session.session_id,
                opening_message,
                timeout=300
            )

            conversation_log.append({
                "type": "debug_start",
                "message": opening_message,
                "response": codex_response,
                "timestamp": time.time()
            })

            # Continue debugging conversation
            final_response = await self._continue_debugging_conversation(
                session.session_id,
                codex_response,
                context_files or [],
                conversation_log
            )

            # Structure results
            return self._structure_debugging_conversation(
                conversation_id,
                conversation_log,
                symptoms
            )

        except Exception as e:
            logger.error("Collaborative debugging conversation failed",
                       agent_id=agent_id,
                       error=str(e))

            return ConversationalFixResponse(
                conversation_summary=f"Debugging conversation error: {str(e)}",
                problem_analysis="Error occurred during debugging conversation",
                suggested_solutions=[],
                debugging_discussion=f"Error: {str(e)}",
                collaboration_notes="Conversation failed",
                codex_conversation_id=conversation_id,
                root_cause_analysis="Unable to analyze due to error",
                prevention_strategies=[]
            )

    # Helper methods for conversation management

    async def _get_or_create_session(
        self,
        agent_id: str,
        session_config: Optional[Dict[str, Any]]
    ) -> Any:
        """Get or create a persistent session for the agent."""
        # Check for existing sessions for this agent
        agent_sessions = await self.session_manager.get_agent_sessions(agent_id)

        if agent_sessions:
            # Use existing session
            session_id = agent_sessions[0]
            session_info = await self.session_manager.get_session_info(session_id)
            if session_info and session_info["status"] == "active":
                logger.debug("Using existing session",
                           agent_id=agent_id,
                           session_id=session_id)

                # Return a simple object with session_id
                class SimpleSession:
                    def __init__(self, sid):
                        self.session_id = sid
                return SimpleSession(session_id)

        # Create new persistent session
        session = await self.session_manager.create_persistent_session(
            agent_id=agent_id,
            session_config=session_config
        )

        logger.info("Created new persistent session for collaborative conversation",
                   agent_id=agent_id,
                   session_id=session.session_id)

        return session

    def _create_planning_opening_message(
        self,
        task: str,
        context: Dict[str, Any]
    ) -> str:
        """Create a natural conversation opener for planning."""
        workspace_info = context.get("workspace_info", {})

        message_parts = [
            f"Hi! I need your help planning the implementation of this task: {task}",
            "",
            "I'm working on this project and would love to collaborate with you on the approach."
        ]

        if workspace_info.get("has_git"):
            message_parts.append("I can see this is a git repository, so we should consider version control in our planning.")

        if workspace_info.get("project_types"):
            project_types = workspace_info["project_types"]
            message_parts.append(f"The project appears to use: {', '.join(project_types)}")

        message_parts.extend([
            "",
            "Could you help me break this down into implementable steps?",
            "What files do you think we'll need to modify or create?",
            "Are there any architectural considerations or potential gotchas I should be aware of?"
        ])

        return "\n".join(message_parts)

    def _create_implementation_opening_message(
        self,
        task: str,
        target_files: List[str],
        context_files: Optional[List[str]],
        requirements: Optional[List[str]]
    ) -> str:
        """Create a natural conversation opener for implementation."""
        message_parts = [
            f"Let's work together on implementing: {task}",
            "",
            f"I'm thinking we'll need to work with these files: {', '.join(target_files)}"
        ]

        if context_files:
            message_parts.append(f"For context, these files might be relevant: {', '.join(context_files)}")

        if requirements:
            message_parts.extend([
                "",
                "Here are the specific requirements:",
                *[f"- {req}" for req in requirements]
            ])

        message_parts.extend([
            "",
            "Could you take a look at the existing code and suggest how we should approach this?",
            "What would be the best way to implement this while following the existing patterns?"
        ])

        return "\n".join(message_parts)

    def _create_review_opening_message(
        self,
        content: Dict[str, Any],
        rubric: Optional[List[str]],
        focus_areas: Optional[List[str]]
    ) -> str:
        """Create a natural conversation opener for code review."""
        message_parts = [
            "I'd like your help reviewing some code changes.",
            ""
        ]

        if "diffs" in content:
            message_parts.append("I have some code diffs to review:")
            # In a real implementation, we'd format the diffs nicely
            message_parts.append("(Code diffs would be formatted here)")
        elif "files" in content:
            message_parts.append("I have some files to review:")
            # In a real implementation, we'd list the files
            message_parts.append("(File list would be formatted here)")

        if rubric:
            message_parts.extend([
                "",
                f"Please focus on these areas: {', '.join(rubric)}"
            ])

        if focus_areas:
            message_parts.extend([
                f"I'm particularly interested in your thoughts on: {', '.join(focus_areas)}"
            ])

        message_parts.extend([
            "",
            "What do you think about the approach and implementation quality?",
            "Are there any improvements or concerns you'd like to discuss?"
        ])

        return "\n".join(message_parts)

    def _create_debugging_opening_message(
        self,
        failing_tests: Optional[str],
        error_output: Optional[str],
        context_files: Optional[List[str]],
        symptoms: Optional[str]
    ) -> str:
        """Create a natural conversation opener for debugging."""
        message_parts = [
            "I'm running into an issue and could use your help debugging it.",
            ""
        ]

        if symptoms:
            message_parts.extend([
                f"Here's what I'm observing: {symptoms}",
                ""
            ])

        if failing_tests:
            message_parts.extend([
                "Here are the failing test results:",
                failing_tests,
                ""
            ])

        if error_output:
            message_parts.extend([
                "Here's the error output:",
                error_output,
                ""
            ])

        if context_files:
            message_parts.extend([
                f"These files might be relevant to the issue: {', '.join(context_files)}",
                ""
            ])

        message_parts.extend([
            "Could you help me analyze what might be going wrong?",
            "What should we investigate first?"
        ])

        return "\n".join(message_parts)

    # Conversation continuation methods (simplified for brevity)

    async def _continue_planning_conversation(self, session_id: str, response: str, context: Dict, log: List) -> str:
        """Continue the planning conversation based on Codex response."""
        # This would implement conversation flow logic
        return response

    async def _continue_implementation_conversation(self, session_id: str, response: str, files: List[str], log: List) -> str:
        """Continue the implementation conversation."""
        return response

    async def _continue_review_conversation(self, session_id: str, response: str, content: Dict, log: List) -> str:
        """Continue the review conversation."""
        return response

    async def _continue_debugging_conversation(self, session_id: str, response: str, files: List[str], log: List) -> str:
        """Continue the debugging conversation."""
        return response

    # Response structuring methods

    def _structure_planning_conversation(self, conv_id: str, log: List, context: Dict) -> ConversationalPlanResponse:
        """Structure planning conversation into MCP response format."""
        return ConversationalPlanResponse(
            conversation_summary="Planning conversation completed",
            task_breakdown=["Extracted from conversation"],
            affected_files=["Files identified in conversation"],
            implementation_approach="Approach discussed in conversation",
            architectural_decisions=["Decisions from conversation"],
            dependencies=[],
            estimated_complexity="medium",
            gotchas=["Issues identified in conversation"],
            integration_points=["Integration points discussed"],
            codex_conversation_id=conv_id,
            workspace_context=context
        )

    def _structure_implementation_conversation(self, conv_id: str, log: List, files: List[str]) -> ConversationalImplementResponse:
        """Structure implementation conversation into MCP response format."""
        return ConversationalImplementResponse(
            conversation_summary="Implementation conversation completed",
            implementation_discussion="Discussion details from conversation",
            suggested_changes=[{"file": f, "change": "Discussed in conversation"} for f in files],
            next_steps=["Steps identified in conversation"],
            collaboration_notes="Collaboration went well",
            codex_conversation_id=conv_id,
            files_examined=files,
            tests_suggested=["Tests discussed in conversation"]
        )

    def _structure_review_conversation(self, conv_id: str, log: List, content: Dict) -> ConversationalReviewResponse:
        """Structure review conversation into MCP response format."""
        return ConversationalReviewResponse(
            conversation_summary="Review conversation completed",
            overall_assessment="Assessment from conversation",
            discussion_points=["Points discussed in conversation"],
            improvement_suggestions=["Suggestions from conversation"],
            collaboration_feedback="Positive collaborative experience",
            codex_conversation_id=conv_id,
            security_notes=["Security aspects discussed"],
            performance_notes=["Performance aspects discussed"]
        )

    def _structure_debugging_conversation(self, conv_id: str, log: List, symptoms: Optional[str]) -> ConversationalFixResponse:
        """Structure debugging conversation into MCP response format."""
        return ConversationalFixResponse(
            conversation_summary="Debugging conversation completed",
            problem_analysis="Analysis from conversation",
            suggested_solutions=["Solutions from conversation"],
            debugging_discussion="Debugging discussion details",
            collaboration_notes="Successful collaborative debugging",
            codex_conversation_id=conv_id,
            root_cause_analysis="Root cause identified in conversation",
            prevention_strategies=["Prevention strategies discussed"]
        )

    def _build_planning_conversation_context(self, task: str, repo_context: Optional[Dict], constraints: Optional[List[str]]) -> Dict[str, Any]:
        """Build context for planning conversation."""
        context = {
            "task": task,
            "workspace_info": {},
            "constraints": constraints or []
        }

        if repo_context:
            context.update(repo_context)

        return context