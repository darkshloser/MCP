"""Configuration management for MCP Platform.

Supports YAML configuration files and environment variable overrides.
Configuration is loaded once and cached for performance.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """LLM provider configuration."""
    provider: str = Field(default="azure_openai", description="LLM provider: azure_openai, openai")
    model: str = Field(default="gpt-4", description="Model name")
    api_key: Optional[str] = Field(default=None, description="API key")
    api_base: Optional[str] = Field(default=None, description="API base URL")
    api_version: Optional[str] = Field(default="2024-02-15-preview", description="API version")
    deployment_name: Optional[str] = Field(default=None, description="Azure deployment name")
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=4096, gt=0)
    
    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=".env",
        extra="ignore"
    )


class MCPServerSettings(BaseSettings):
    """MCP Server configuration."""
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8001)
    domains_path: str = Field(default="config/domains")
    enable_audit: bool = Field(default=True)
    audit_log_path: str = Field(default="logs/audit.log")
    
    # Security
    require_auth: bool = Field(default=True)
    trusted_clients: list[str] = Field(default_factory=lambda: ["orchestrator"])
    
    model_config = SettingsConfigDict(
        env_prefix="MCP_SERVER_",
        env_file=".env",
        extra="ignore"
    )


class OrchestratorSettings(BaseSettings):
    """Orchestrator configuration."""
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    mcp_server_url: str = Field(default="http://localhost:8001")
    
    # Conversation
    max_conversation_length: int = Field(default=50)
    conversation_ttl_minutes: int = Field(default=60)
    
    # Security
    secret_key: str = Field(default="change-me-in-production")
    token_expire_minutes: int = Field(default=60)
    
    model_config = SettingsConfigDict(
        env_prefix="ORCHESTRATOR_",
        env_file=".env",
        extra="ignore"
    )


class Settings(BaseSettings):
    """Main application settings."""
    environment: str = Field(default="development")
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")
    
    # Component settings
    llm: LLMSettings = Field(default_factory=LLMSettings)
    mcp_server: MCPServerSettings = Field(default_factory=MCPServerSettings)
    orchestrator: OrchestratorSettings = Field(default_factory=OrchestratorSettings)
    
    model_config = SettingsConfigDict(
        env_prefix="MCP_",
        env_file=".env",
        extra="ignore"
    )
    
    @classmethod
    def from_yaml(cls, path: str | Path) -> "Settings":
        """Load settings from a YAML file."""
        path = Path(path)
        if not path.exists():
            return cls()
        
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        
        return cls(**data)


def load_yaml_config(path: str | Path) -> dict[str, Any]:
    """Load a YAML configuration file."""
    path = Path(path)
    if not path.exists():
        return {}
    
    with open(path) as f:
        return yaml.safe_load(f) or {}


def save_yaml_config(data: dict[str, Any], path: str | Path) -> None:
    """Save configuration to a YAML file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    config_path = os.environ.get("MCP_CONFIG_PATH", "config/settings.yaml")
    return Settings.from_yaml(config_path)


def get_domain_configs(domains_path: str = "config/domains") -> dict[str, dict[str, Any]]:
    """Load all domain configurations."""
    path = Path(domains_path)
    configs = {}
    
    if not path.exists():
        return configs
    
    for config_file in path.glob("*.yaml"):
        domain_name = config_file.stem
        configs[domain_name] = load_yaml_config(config_file)
    
    return configs
