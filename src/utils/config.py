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


# Valid GPT-5 models and reasoning levels
VALID_GPT5_MODELS = {
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-nano",
    "gpt-5-codex"
}

VALID_REASONING_LEVELS = {
    "low",
    "medium",
    "high"
}


def validate_codex_config(config: 'CodexConfig') -> None:
    """
    Validate Codex configuration with strict model and reasoning checks.

    Args:
        config: CodexConfig instance to validate

    Raises:
        ValueError: If model or reasoning configuration is invalid
    """
    # Strict model validation - no fallbacks
    if config.model not in VALID_GPT5_MODELS:
        raise ValueError(
            f"Invalid CODEX_MODEL '{config.model}'. "
            f"Must be one of: {', '.join(sorted(VALID_GPT5_MODELS))}. "
            f"No fallback models are supported."
        )

    # Strict reasoning validation
    if config.reasoning not in VALID_REASONING_LEVELS:
        raise ValueError(
            f"Invalid CODEX_REASONING '{config.reasoning}'. "
            f"Must be one of: {', '.join(sorted(VALID_REASONING_LEVELS))}"
        )


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
    model: str = "gpt-5-codex"  # Default to preferred model
    reasoning: str = "medium"  # Reasoning level: low, medium, high
    provider: str = "openai"
    approval_mode: str = "suggest"
    error_mode: str = "ask-user"
    notify: bool = False


@dataclass
class OAuthConfig:
    """OAuth-specific configuration."""
    client_id: str = "codex-cli"
    authorization_endpoint: str = "https://auth.openai.com/oauth/authorize"
    token_endpoint: str = "https://auth.openai.com/oauth/token"
    revoke_endpoint: str = "https://auth.openai.com/oauth/revoke"
    callback_port: int = 8765
    callback_timeout: int = 300  # 5 minutes
    scope: str = "openai-api"
    auto_open_browser: bool = True
    token_storage_path: Optional[str] = None  # Defaults to ~/.codex/auth.json


@dataclass
class AuthConfig:
    """Authentication configuration - OpenAI and OAuth."""
    openai_api_key: Optional[str] = None
    chatgpt_oauth_token: Optional[str] = None
    auth_method: str = "auto"  # "auto", "api_key", or "oauth"
    prefer_oauth: bool = True  # Prefer OAuth over API key when both available
    oauth: OAuthConfig = field(default_factory=OAuthConfig)


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

    # Validate Codex configuration with strict checks
    validate_codex_config(config.codex)

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
    config.codex.reasoning = os.getenv("CODEX_REASONING", config.codex.reasoning)
    config.codex.provider = os.getenv("CODEX_PROVIDER", config.codex.provider)
    config.codex.approval_mode = os.getenv("CODEX_APPROVAL_MODE", config.codex.approval_mode)

    # Auth config - OpenAI and OAuth
    config.auth.openai_api_key = os.getenv("OPENAI_API_KEY")
    config.auth.chatgpt_oauth_token = os.getenv("CHATGPT_OAUTH_TOKEN")
    config.auth.auth_method = os.getenv("CODEX_AUTH_METHOD", "auto")
    config.auth.prefer_oauth = os.getenv("CODEX_PREFER_OAUTH", "true").lower() == "true"

    # OAuth-specific config
    config.auth.oauth.client_id = os.getenv("OAUTH_CLIENT_ID", config.auth.oauth.client_id)
    config.auth.oauth.authorization_endpoint = os.getenv("OAUTH_AUTHORIZATION_ENDPOINT", config.auth.oauth.authorization_endpoint)
    config.auth.oauth.token_endpoint = os.getenv("OAUTH_TOKEN_ENDPOINT", config.auth.oauth.token_endpoint)
    config.auth.oauth.revoke_endpoint = os.getenv("OAUTH_REVOKE_ENDPOINT", config.auth.oauth.revoke_endpoint)
    config.auth.oauth.callback_port = int(os.getenv("OAUTH_CALLBACK_PORT", str(config.auth.oauth.callback_port)))
    config.auth.oauth.callback_timeout = int(os.getenv("OAUTH_CALLBACK_TIMEOUT", str(config.auth.oauth.callback_timeout)))
    config.auth.oauth.scope = os.getenv("OAUTH_SCOPE", config.auth.oauth.scope)
    config.auth.oauth.auto_open_browser = os.getenv("OAUTH_AUTO_OPEN_BROWSER", "true").lower() == "true"
    config.auth.oauth.token_storage_path = os.getenv("OAUTH_TOKEN_STORAGE_PATH")


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
                if key == "oauth" and isinstance(value, dict):
                    # Handle nested OAuth configuration
                    for oauth_key, oauth_value in value.items():
                        if hasattr(config.auth.oauth, oauth_key):
                            setattr(config.auth.oauth, oauth_key, oauth_value)
                elif hasattr(config.auth, key):
                    setattr(config.auth, key, value)

    except Exception as e:
        raise RuntimeError(f"Failed to load config from {config_path}: {e}")


def get_config() -> Config:
    """Get the current configuration instance."""
    return load_config()