"""Runtime configuration loaded from environment / git-ignored .env.

Athenaeum never hardcodes secrets. Build-time auth prefers DefaultAzureCredential
(your `az login`); API keys are accepted as a fallback for local convenience.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_DIR = Path(__file__).resolve().parents[1]
CONTENT_DIR = REPO_DIR / "content"
GROUNDING_DIR = REPO_DIR / "grounding"
CATALOG_PATH = CONTENT_DIR / "_catalog.json"


class Settings(BaseSettings):
    """Athenaeum settings. Values come from environment variables or a git-ignored .env."""

    model_config = SettingsConfigDict(
        env_file=str(REPO_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Foundry / Azure OpenAI
    foundry_project_endpoint: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-21"
    embed_deployment: str = "text-embedding-3-large"
    embed_model: str = "text-embedding-3-large"
    embed_dimensions: int = 3072
    gpt_deployment: str = "gpt-4o-mini"

    # Azure AI Search (Foundry IQ host)
    search_endpoint: str = ""
    search_admin_key: str = ""
    search_api_version: str = "2025-08-01-preview"

    # Provisioning targets
    azure_location: str = "eastus2"
    search_resource_group: str = "rg-athenaeum"
    search_service_name: str = "athenaeum-search"
    search_sku: str = "basic"
    aoai_account_name: str = "ajayaditya-msf-resource"
    aoai_resource_group: str = "NetworkWatcherRG"

    # Index / KB names
    index_name: str = "athenaeum-courses"
    knowledge_source_name: str = "athenaeum-course-source"
    knowledge_base_name: str = "athenaeum-knowledge-base"
    # Populated after ingest; the knowledge_base_retrieve MCP endpoint for Foundry agents.
    knowledge_base_mcp_endpoint: str = ""

    content_dir: Path = Field(default=CONTENT_DIR)
    catalog_path: Path = Field(default=CATALOG_PATH)

    def require(self, *names: str) -> None:
        """Fail fast with a clear message if required settings are missing."""
        missing = [n for n in names if not getattr(self, n, None)]
        if missing:
            raise RuntimeError(
                f"Missing required settings: {', '.join(missing)}. "
                f"Fill them in {REPO_DIR / '.env'} (run `athenaeum provision` for Search values)."
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
