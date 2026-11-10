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

    content_dir: Path = Field(default=CONTENT_DIR)
    catalog_path: Path = Field(default=CATALOG_PATH)

    def require(self, *names: str) -> None:
        """Fail fast with a clear message if required settings are missing."""
        missing = [n for n in names if not getattr(self, n, None)]
        if missing:
            raise RuntimeError(
                f"Missing required settings: {', '.join(missing)}. "
                f"Fill them in {REPO_DIR / '.env'}."
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
