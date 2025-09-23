"""
Persistent storage for agent-container mappings and metadata.

This module handles the persistent storage of agent container relationships,
session metadata, and container state across server restarts.
"""

import json
import time
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

import structlog

logger = structlog.get_logger(__name__)


class ContainerStatus(Enum):
    """Container status states."""
    CREATING = "creating"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class AgentContainerInfo:
    """Information about an agent's container."""
    agent_id: str
    container_id: str
    container_name: str
    created_at: float
    last_active: float
    status: ContainerStatus
    workspace_path: str
    config_path: str
    model: str = "gpt-5"
    provider: str = "openai"
    approval_mode: str = "suggest"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data['status'] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentContainerInfo':
        """Create from dictionary."""
        data['status'] = ContainerStatus(data['status'])
        return cls(**data)


class AgentPersistenceManager:
    """
    Manages persistent storage of agent-container relationships.

    Handles:
    - Agent-to-container mappings
    - Container metadata and state
    - Session persistence across server restarts
    - Cleanup of stale containers
    """

    def __init__(self, data_path: str = "./data"):
        """
        Initialize persistence manager.

        Args:
            data_path: Path to persistent data directory
        """
        self.data_path = Path(data_path)
        self.metadata_file = self.data_path / "metadata" / "agent_containers.json"
        self.lock = asyncio.Lock()

        # Ensure directories exist
        self.data_path.mkdir(exist_ok=True)
        (self.data_path / "metadata").mkdir(exist_ok=True)
        (self.data_path / "agents").mkdir(exist_ok=True)

        # Initialize data structure
        self._data: Dict[str, AgentContainerInfo] = {}
        self._load_data()

        logger.info("Agent persistence manager initialized",
                   data_path=str(self.data_path),
                   existing_agents=len(self._data))

    def _load_data(self) -> None:
        """Load agent-container mappings from disk."""
        try:
            if self.metadata_file.exists():
                with open(self.metadata_file, 'r') as f:
                    data = json.load(f)

                self._data = {
                    agent_id: AgentContainerInfo.from_dict(info)
                    for agent_id, info in data.items()
                }

                logger.debug("Loaded agent data from disk",
                           agent_count=len(self._data))
            else:
                self._data = {}
                logger.debug("No existing agent data found, starting fresh")

        except Exception as e:
            logger.error("Failed to load agent data, starting fresh",
                        error=str(e))
            self._data = {}

    async def _save_data(self) -> None:
        """Save agent-container mappings to disk."""
        try:
            # Ensure metadata directory exists
            self.metadata_file.parent.mkdir(exist_ok=True)

            # Convert to serializable format
            serializable_data = {
                agent_id: info.to_dict()
                for agent_id, info in self._data.items()
            }

            # Write atomically
            temp_file = self.metadata_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(serializable_data, f, indent=2)

            # Atomic move
            temp_file.replace(self.metadata_file)

            logger.debug("Saved agent data to disk",
                        agent_count=len(self._data))

        except Exception as e:
            logger.error("Failed to save agent data", error=str(e))
            raise

    async def register_agent_container(
        self,
        agent_id: str,
        container_id: str,
        container_name: str,
        workspace_path: str,
        config_path: str,
        model: str = "gpt-5",
        provider: str = "openai",
        approval_mode: str = "suggest"
    ) -> None:
        """
        Register a new agent-container mapping.

        Args:
            agent_id: Unique agent identifier
            container_id: Docker container ID
            container_name: Docker container name
            workspace_path: Path to agent's workspace
            config_path: Path to agent's config
            model: Codex model to use
            provider: AI provider
            approval_mode: Approval mode for Codex
        """
        async with self.lock:
            current_time = time.time()

            info = AgentContainerInfo(
                agent_id=agent_id,
                container_id=container_id,
                container_name=container_name,
                created_at=current_time,
                last_active=current_time,
                status=ContainerStatus.CREATING,
                workspace_path=workspace_path,
                config_path=config_path,
                model=model,
                provider=provider,
                approval_mode=approval_mode
            )

            self._data[agent_id] = info
            await self._save_data()

            logger.info("Registered agent container",
                       agent_id=agent_id,
                       container_id=container_id[:12])

    async def get_agent_container(self, agent_id: str) -> Optional[AgentContainerInfo]:
        """
        Get container information for an agent.

        Args:
            agent_id: Agent identifier

        Returns:
            AgentContainerInfo: Container info if exists, None otherwise
        """
        async with self.lock:
            return self._data.get(agent_id)

    async def update_container_status(
        self,
        agent_id: str,
        status: ContainerStatus
    ) -> None:
        """
        Update container status for an agent.

        Args:
            agent_id: Agent identifier
            status: New container status
        """
        async with self.lock:
            if agent_id in self._data:
                self._data[agent_id].status = status
                self._data[agent_id].last_active = time.time()
                await self._save_data()

                logger.debug("Updated container status",
                           agent_id=agent_id,
                           status=status.value)

    async def update_last_active(self, agent_id: str) -> None:
        """
        Update last active timestamp for an agent.

        Args:
            agent_id: Agent identifier
        """
        async with self.lock:
            if agent_id in self._data:
                self._data[agent_id].last_active = time.time()
                await self._save_data()

    async def remove_agent_container(self, agent_id: str) -> Optional[AgentContainerInfo]:
        """
        Remove agent-container mapping.

        Args:
            agent_id: Agent identifier

        Returns:
            AgentContainerInfo: Removed container info if existed
        """
        async with self.lock:
            info = self._data.pop(agent_id, None)
            if info:
                await self._save_data()

                logger.info("Removed agent container mapping",
                           agent_id=agent_id,
                           container_id=info.container_id[:12])

            return info

    async def list_all_agents(self) -> List[AgentContainerInfo]:
        """
        List all registered agent containers.

        Returns:
            List[AgentContainerInfo]: List of all agent container info
        """
        async with self.lock:
            return list(self._data.values())

    async def list_active_agents(self) -> List[AgentContainerInfo]:
        """
        List agents with running containers.

        Returns:
            List[AgentContainerInfo]: List of active agent container info
        """
        async with self.lock:
            return [
                info for info in self._data.values()
                if info.status == ContainerStatus.RUNNING
            ]

    async def list_inactive_agents(self, inactive_threshold: int = 3600) -> List[AgentContainerInfo]:
        """
        List agents that have been inactive for a specified time.

        Args:
            inactive_threshold: Seconds of inactivity to consider inactive

        Returns:
            List[AgentContainerInfo]: List of inactive agent container info
        """
        async with self.lock:
            current_time = time.time()
            return [
                info for info in self._data.values()
                if (current_time - info.last_active) > inactive_threshold
            ]

    async def cleanup_stale_entries(self, max_age: int = 86400) -> List[str]:
        """
        Remove entries for containers that no longer exist or are very old.

        Args:
            max_age: Maximum age in seconds before considering stale

        Returns:
            List[str]: List of removed agent IDs
        """
        async with self.lock:
            current_time = time.time()
            removed_agents = []

            for agent_id, info in list(self._data.items()):
                # Remove very old entries
                if (current_time - info.created_at) > max_age:
                    self._data.pop(agent_id)
                    removed_agents.append(agent_id)

                    logger.info("Removed stale agent entry",
                               agent_id=agent_id,
                               age_hours=(current_time - info.created_at) / 3600)

            if removed_agents:
                await self._save_data()

            return removed_agents

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about agent containers.

        Returns:
            Dict[str, Any]: Statistics dictionary
        """
        async with self.lock:
            total = len(self._data)
            running = sum(1 for info in self._data.values() if info.status == ContainerStatus.RUNNING)
            stopped = sum(1 for info in self._data.values() if info.status == ContainerStatus.STOPPED)
            error = sum(1 for info in self._data.values() if info.status == ContainerStatus.ERROR)

            current_time = time.time()
            recently_active = sum(
                1 for info in self._data.values()
                if (current_time - info.last_active) < 3600  # Active in last hour
            )

            return {
                "total_agents": total,
                "running_containers": running,
                "stopped_containers": stopped,
                "error_containers": error,
                "recently_active": recently_active,
                "data_path": str(self.data_path),
                "metadata_file": str(self.metadata_file)
            }