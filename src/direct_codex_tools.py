"""Direct Codex MCP tools (non-conversational).

These tools provide straightforward plan/implement/review/fix operations
where the MCP server sends a single prompt to Codex, waits for the final
response, and returns parsed structured data without conversational loop.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import structlog

from .session_manager import CodexSessionManager, AgentSession

logger = structlog.get_logger(__name__)


@dataclass
class PromptTemplate:
    name: str
    instruction: str


PLAN_TEMPLATE = PromptTemplate(
    name="plan",
    instruction=(
        "You are Codex, generating a detailed plan for the requested task. "
        "Respond strictly as JSON matching the following schema:\n"
        "{\n"
        "  \"task_breakdown\": [\"step 1\", ...],\n"
        "  \"affected_files\": [\"path/to/file\", ...],\n"
        "  \"implementation_approach\": \"...\",\n"
        "  \"architectural_decisions\": [\"...\"],\n"
        "  \"dependencies\": [\"...\"],\n"
        "  \"estimated_complexity\": \"low|medium|high\",\n"
        "  \"gotchas\": [\"...\"],\n"
        "  \"integration_points\": [\"...\"]\n"
        "}\n"
        "Include no additional commentary outside the JSON object."
    ),
)


class DirectCodexTools:
    """Simplified tool layer that uses a single-turn Codex interaction."""

    def __init__(self, session_manager: CodexSessionManager) -> None:
        self.session_manager = session_manager
        self.container_manager = session_manager.container_manager

    async def plan(
        self,
        agent_id: str,
        task: str,
        repo_context: Optional[Dict[str, Any]] = None,
        constraints: Optional[List[str]] = None,
        session_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate a plan from a Codex session."""
        container_session = await self.container_manager.get_or_create_persistent_agent_container(
            agent_id=agent_id,
            model=(session_config or {}).get("model", self.session_manager.config.codex.model),
            provider=(session_config or {}).get("provider", self.session_manager.config.codex.provider),
            approval_mode=(session_config or {}).get("approval_mode", self.session_manager.config.codex.approval_mode),
            reasoning=(session_config or {}).get("reasoning", self.session_manager.config.codex.reasoning),
        )

        prompt = self._build_plan_prompt(task, repo_context, constraints)

        logger.info(
            "Direct Codex plan request",
            agent_id=agent_id,
            session_id=container_session.session_id,
        )

        response = await self.container_manager.send_message_to_codex(
            container_session,
            prompt,
            timeout=600,
        )

        logger.info("Codex plan response received", length=len(response))

        return self._parse_plan_response(response)



    def _build_plan_prompt(
        self,
        task: str,
        repo_context: Optional[Dict[str, Any]],
        constraints: Optional[List[str]],
    ) -> str:
        sections = [PLAN_TEMPLATE.instruction, "", "TASK DESCRIPTION:", task.strip(), ""]

        if repo_context:
            sections.append("REPOSITORY CONTEXT:")
            sections.append(json.dumps(repo_context, indent=2))
            sections.append("")

        if constraints:
            sections.append("CONSTRAINTS:")
            sections.append("\n".join(f"- {c}" for c in constraints))
            sections.append("")

        sections.append("Please return only the JSON object; do not include commentary.")
        return "\n".join(filter(None, sections))

    def _parse_plan_response(self, response: str) -> Dict[str, Any]:
        response = response.strip()
        if not response:
            raise ValueError("Received empty response from Codex")

        # Codex may include extra commentary; try to extract JSON block
        candidates: List[str] = []

        # Primary attempt: entire response (stripped)
        candidates.append(response)

        # Extract substring between first "{" and matching "}" if present
        start = response.find("{")
        end = response.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidates.append(response[start:end + 1])

        # Split by code fences or markers that might wrap JSON
        if "```" in response:
            for block in response.split("```"):
                block = block.strip()
                if block.startswith("{") and block.endswith("}"):
                    candidates.append(block)

        for candidate in candidates:
            candidate = candidate.strip()
            if not candidate:
                continue
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue

        logger.warning(
            "Falling back to legacy planning parser",
            response_preview=response[:300],
        )
        fallback = self._parse_legacy_plan_response(response)
        if fallback:
            return fallback

        logger.error(
            "Failed to parse Codex planning response",
            response_preview=response[:500],
        )
        raise ValueError("Codex response was not valid JSON")

    def _parse_legacy_plan_response(self, response: str) -> Optional[Dict[str, Any]]:
        lines = [line.strip() for line in response.splitlines() if line.strip()]
        if not lines:
            return None

        sections: Dict[str, List[str]] = {
            "breakdown": [],
            "files": [],
            "approach": [],
            "decisions": [],
            "dependencies": [],
            "gotchas": [],
            "integration": [],
        }

        current = None
        for line in lines:
            upper = line.upper()
            if "TASK BREAKDOWN" in upper:
                current = "breakdown"
                continue
            if "AFFECTED FILES" in upper:
                current = "files"
                continue
            if "IMPLEMENTATION APPROACH" in upper:
                current = "approach"
                continue
            if "ARCHITECTURAL DECISIONS" in upper:
                current = "decisions"
                continue
            if "DEPENDENCIES" in upper:
                current = "dependencies"
                continue
            if "GOTCHAS" in upper:
                current = "gotchas"
                continue
            if "INTEGRATION POINTS" in upper:
                current = "integration"
                continue

            if current:
                sections[current].append(line)

        # If we never detected sections, treat entire response as a single paragraph
        if all(not values for values in sections.values()):
            return {
                "task_breakdown": [response],
                "affected_files": [],
                "implementation_approach": response,
                "architectural_decisions": [],
                "dependencies": [],
                "estimated_complexity": "medium",
                "gotchas": [],
                "integration_points": [],
            }

        return {
            "task_breakdown": sections["breakdown"] or [response],
            "affected_files": sections["files"],
            "implementation_approach": "\n".join(sections["approach"]) or response,
            "architectural_decisions": sections["decisions"],
            "dependencies": sections["dependencies"],
            "estimated_complexity": "medium",
            "gotchas": sections["gotchas"],
            "integration_points": sections["integration"],
        }
