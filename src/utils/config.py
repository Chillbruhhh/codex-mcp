"""
Configuration management for the Codex CLI MCP Server.

This module handles loading configuration from environment variables,
config files, and provides default values for all server settings.
"""

import os
from typing import Optional, Dict, Any
from pathlib import Path
from dataclasses import dataclass, field

import tomli
from dotenv import load_dotenv


@dataclass
class ServerConfig:
    """Main server configuration."""
    host: str = "localhost"
    port: int = 8000
    log_level: str = "INFO"
    max_concurrent_sessions: int = 20
    session_timeout: int = 3600  # 1 hour


@dataclass
class ContainerConfig:
    """Docker container configuration."""
    cpu_limit: str = "4.0"  # Further increased to handle potential resource spikes
    memory_limit: str = "2048m"  # Doubled memory for better headroom
    network_mode: str = "codex-mcp-network"
    auto_remove: bool = True
    restart_policy: str = "no"


@dataclass
class CodexConfig:
    """Codex CLI configuration."""
    model: str = "gpt-5"  # Codex CLI only supports GPT-5
    provider: str = "openai"
    approval_mode: str = "suggest"
    error_mode: str = "ask-user"
    notify: bool = False


@dataclass
class AuthConfig:
    """Authentication configuration - OpenAI only."""
    openai_api_key: Optional[str] = None
    chatgpt_oauth_token: Optional[str] = None
    auth_method: str = "auto"  # "auto", "api_key", or "oauth"


@dataclass
class Config:
    """Complete application configuration."""
    server: ServerConfig = field(default_factory=ServerConfig)
    container: ContainerConfig = field(default_factory=ContainerConfig)
    codex: CodexConfig = field(default_factory=CodexConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)


def load_config(config_path: Optional[str] = None) -> Config:
    """
    Load configuration from environment variables and config files.

    Args:
        config_path: Optional path to TOML config file

    Returns:
        Config: Loaded configuration object
    """
    # Load environment variables from .env file if it exists
    load_dotenv()

    config = Config()

    # Load from environment variables
    _load_from_env(config)

    # Load from config file if provided
    if config_path and Path(config_path).exists():
        _load_from_file(config, config_path)

    return config


def _load_from_env(config: Config) -> None:
    """Load configuration values from environment variables."""
    # Server config
    config.server.host = os.getenv("MCP_HOST", config.server.host)
    config.server.port = int(os.getenv("MCP_PORT", str(config.server.port)))
    config.server.log_level = os.getenv("LOG_LEVEL", config.server.log_level)
    config.server.max_concurrent_sessions = int(
        os.getenv("MAX_CONCURRENT_SESSIONS", str(config.server.max_concurrent_sessions))
    )
    config.server.session_timeout = int(
        os.getenv("SESSION_TIMEOUT", str(config.server.session_timeout))
    )

    # Container config
    config.container.cpu_limit = os.getenv("CONTAINER_CPU_LIMIT", config.container.cpu_limit)
    config.container.memory_limit = os.getenv("CONTAINER_MEMORY_LIMIT", config.container.memory_limit)
    config.container.network_mode = os.getenv("CONTAINER_NETWORK_MODE", config.container.network_mode)

    # Codex config
    config.codex.model = os.getenv("CODEX_MODEL", config.codex.model)
    config.codex.provider = os.getenv("CODEX_PROVIDER", config.codex.provider)
    config.codex.approval_mode = os.getenv("CODEX_APPROVAL_MODE", config.codex.approval_mode)

    # Auth config - OpenAI only
    config.auth.openai_api_key = os.getenv("OPENAI_API_KEY")
    config.auth.chatgpt_oauth_token = os.getenv("CHATGPT_OAUTH_TOKEN")
    config.auth.auth_method = os.getenv("CODEX_AUTH_METHOD", "auto")


def _load_from_file(config: Config, config_path: str) -> None:
    """Load configuration from TOML file."""
    try:
        with open(config_path, "rb") as f:
            data = tomli.load(f)

        # Update config with file values
        if "server" in data:
            for key, value in data["server"].items():
                if hasattr(config.server, key):
                    setattr(config.server, key, value)

        if "container" in data:
            for key, value in data["container"].items():
                if hasattr(config.container, key):
                    setattr(config.container, key, value)

        if "codex" in data:
            for key, value in data["codex"].items():
                if hasattr(config.codex, key):
                    setattr(config.codex, key, value)

        if "auth" in data:
            for key, value in data["auth"].items():
                if hasattr(config.auth, key):
                    setattr(config.auth, key, value)

    except Exception as e:
        raise RuntimeError(f"Failed to load config from {config_path}: {e}")


def get_config() -> Config:
    """Get the current configuration instance."""
    return load_config()