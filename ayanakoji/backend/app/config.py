"""Application configuration loaded from environment / .env (never hardcoded secrets)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

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
    model_fast: str


@dataclass(frozen=True)
class GroqConfig:
    """Validated Groq config — the 3rd/4th tier of the model fallback chain (§model-routing)."""

    api_key: str
    base_url: str
    model_workhorse: str
    model_fast: str
    model_reasoning: str


class Settings(BaseSettings):
    """Runtime settings. Values come from environment variables or a git-ignored .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "athenaeum-backend"
    environment: str = "development"

    # Comma-separated list of allowed CORS origins for the Next.js frontend.
    cors_origins: str = "http://localhost:3000"

    # --- Learner workspace persistence (courses, messages, assessments) ---
    # SQLite by default — zero infra, file-based, fully offline. Override per env.
    database_url: str = "sqlite:///./athenaeum.db"

    # --- Assessment question banks (separate DB from the learner workspace) ---
    # Authored per-module question banks live in their own SQLite file so the
    # static question bank never mingles with a learner's live attempt data.
    assessments_database_url: str = "sqlite:///./assessments.db"

    # --- Azure Blob mirror for the question banks (credential-gated) ---
    # Account name only; auth is DefaultAzureCredential (no secrets in repo).
    azure_storage_account: str | None = None
    assessment_blob_container: str = "assessment-banks"

    # Force the deterministic offline LLM path even when Foundry creds are present
    # (used by CI/E2E/smoke so the chat works without live Azure calls).
    offline_llm: bool = False

    # --- Notifications / streak cron ---
    # How often the background tick re-derives notifications + streak for every
    # learner. The read endpoint also ticks lazily, so this only drives toasts for
    # learners who are online but idle. Set to 0 to disable the background loop.
    notify_tick_seconds: int = 60

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
    # Cheap fast-classifier deployment (router / injection-gate). gpt-4o-mini by
    # default; point at a Phi deployment if you have one — capability, not vanity.
    model_fast: str = "gpt-4o-mini"

    # --- Groq (fallback provider; tiers 3 & 4 of the Azure→Azure→Groq→Groq chain) ---
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model_workhorse: str = "llama-3.3-70b-versatile"
    groq_model_fast: str = "llama-3.1-8b-instant"
    groq_model_reasoning: str = "deepseek-r1-distill-llama-70b"
    # Purpose-built prompt-injection/jailbreak classifier (returns a 0..1 score).
    groq_model_guard: str = "meta-llama/llama-prompt-guard-2-86m"
    # Block when the guard's jailbreak probability is at/above this.
    guard_block_threshold: float = 0.8
    # Per-call model timeout (seconds) so a hung provider can't stall a whole turn.
    llm_timeout_seconds: float = 30.0
    # Safety ceiling for LLM-grader exchanges per question. The grader calls
    # grade_answer when confident; this is only reached if it never does.
    assessment_grader_ceiling: int = 8

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
    def groq_configured(self) -> bool:
        """True when a usable Groq API key is present (the fallback provider)."""
        return not _is_placeholder(self.groq_api_key)

    @property
    def llm_offline(self) -> bool:
        """Use the deterministic offline LLM path when forced, or when NO provider is set.

        The agent pipeline can run on Azure *or* Groq; it only drops to the
        deterministic mock when forced (``OFFLINE_LLM=true``) or when neither
        provider is configured (zero-credential demo / CI lane).
        """
        return self.offline_llm or not (self.foundry_configured or self.groq_configured)

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
            model_fast=self.model_fast,
        )

    def require_groq(self) -> GroqConfig:
        """Return a validated GroqConfig or raise loudly if the key is missing."""
        if _is_placeholder(self.groq_api_key):
            raise RuntimeError("Groq not configured — missing/placeholder: GROQ_API_KEY")
        assert self.groq_api_key is not None
        return GroqConfig(
            api_key=self.groq_api_key,
            base_url=self.groq_base_url,
            model_workhorse=self.groq_model_workhorse,
            model_fast=self.groq_model_fast,
            model_reasoning=self.groq_model_reasoning,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return application settings, cached for the process so ``.env`` is read once.

    Every turn touches settings in several nodes (gate, router, answer); without the
    cache each call re-parses the ``.env`` file. The process env is fixed at startup,
    so a single cached instance is correct in production. Tests clear the cache between
    cases (see ``conftest._offline_env``) so per-test env overrides still take effect.
    """
    return Settings()
