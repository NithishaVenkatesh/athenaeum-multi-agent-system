"""Application configuration loaded from environment / .env (never hardcoded secrets)."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_settings import BaseSettings, SettingsConfigDict

# Substrings that mark a value as an unfilled placeholder (fail-loud, build-spec §1).
_PLACEHOLDER_PREFIXES = ("<", "TODO", "changeme", "your-")


def _is_placeholder(value: str | None) -> bool:
    return value is None or value.strip() == "" or value.strip().startswith(_PLACEHOLDER_PREFIXES)


@dataclass(frozen=True)
class FoundryConfig:
    """Validated, non-placeholder Microsoft Foundry / Azure OpenAI configuration."""

    project_endpoint: str
    openai_endpoint: str
    openai_api_key: str
    openai_api_version: str
    model_workhorse: str
    model_reasoning: str
    model_embed: str


class Settings(BaseSettings):
    """Runtime settings. Values come from environment variables or a git-ignored .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ayanakoji-backend"
    environment: str = "development"

    # Comma-separated list of allowed CORS origins for the Next.js frontend.
    cors_origins: str = "http://localhost:3000"

    # --- Learner workspace persistence (courses, messages, assessments) ---
    # SQLite by default — zero infra, file-based, fully offline. Override per env.
    database_url: str = "sqlite:///./ayanakoji.db"

    # Force the deterministic offline LLM path even when Foundry creds are present
    # (used by CI/E2E/smoke so the chat works without live Azure calls).
    offline_llm: bool = False

    # Path to the Athenaeum course catalog JSON. None → resolve the in-repo default.
    athenaeum_catalog_path: str | None = None

    # --- Microsoft Foundry / Azure OpenAI (optional until the agent layer is wired) ---
    foundry_project_endpoint: str | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_api_version: str = "2024-10-21"
    model_workhorse: str = "gpt-4o-mini"
    model_reasoning: str = "o4-mini"
    model_embed: str = "text-embedding-3-large"

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS origins as a clean list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def foundry_configured(self) -> bool:
        """True only when all required Foundry values are present and non-placeholder."""
        return not any(
            _is_placeholder(v)
            for v in (
                self.foundry_project_endpoint,
                self.azure_openai_endpoint,
                self.azure_openai_api_key,
            )
        )

    @property
    def llm_offline(self) -> bool:
        """Use the deterministic offline LLM path when forced or when Foundry is unset."""
        return self.offline_llm or not self.foundry_configured

    def require_foundry(self) -> FoundryConfig:
        """Return a validated FoundryConfig or raise loudly listing what is missing.

        Used by the agent/IQ layer so a misconfiguration fails at the boundary with a
        clear message instead of an opaque SDK error deep in a request.
        """
        missing = [
            name
            for name, value in (
                ("FOUNDRY_PROJECT_ENDPOINT", self.foundry_project_endpoint),
                ("AZURE_OPENAI_ENDPOINT", self.azure_openai_endpoint),
                ("AZURE_OPENAI_API_KEY", self.azure_openai_api_key),
            )
            if _is_placeholder(value)
        ]
        if missing:
            raise RuntimeError(
                "Foundry not configured — missing/placeholder: " + ", ".join(missing)
            )
        # mypy: the checks above guarantee these are non-None.
        assert self.foundry_project_endpoint is not None
        assert self.azure_openai_endpoint is not None
        assert self.azure_openai_api_key is not None
        return FoundryConfig(
            project_endpoint=self.foundry_project_endpoint,
            openai_endpoint=self.azure_openai_endpoint,
            openai_api_key=self.azure_openai_api_key,
            openai_api_version=self.azure_openai_api_version,
            model_workhorse=self.model_workhorse,
            model_reasoning=self.model_reasoning,
            model_embed=self.model_embed,
        )


def get_settings() -> Settings:
    """Return application settings (instantiated per call; cheap and test-friendly)."""
    return Settings()
