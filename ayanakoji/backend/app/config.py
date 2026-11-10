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
class ProviderConfig:
    """Validated config for one OpenAI-compatible chat provider (Groq or Gemini)."""

    api_key: str
    base_url: str
    model_workhorse: str
    model_fast: str
    model_reasoning: str


# Both providers share one shape; the aliases keep call sites self-describing.
GroqConfig = ProviderConfig
GeminiConfig = ProviderConfig


@dataclass(frozen=True)
class VectorSearchConfig:
    """Validated Cohere-embeddings + Qdrant Cloud configuration (the live grounding host).

    Consumed by the cloud adapter (``app.agent.grounding_vector``) only when
    ``vector_search_configured`` is true; otherwise the offline lexical retriever answers.
    """

    cohere_api_key: str
    embed_model: str
    embed_dimensions: int
    qdrant_url: str
    qdrant_api_key: str
    collection: str


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

    # Seed assessments.db at startup from the in-repo JSON banks.
    # CI/tests set this false and seed explicitly so startup stays hermetic.
    seed_assessments_on_startup: bool = True

    # Force the deterministic offline LLM path even when provider keys are present
    # (used by CI/E2E/smoke so the chat works without live model calls).
    offline_llm: bool = False

    # --- Notifications / streak cron ---
    # How often the background tick re-derives notifications + streak for every
    # learner. The read endpoint also ticks lazily, so this only drives toasts for
    # learners who are online but idle. Set to 0 to disable the background loop.
    notify_tick_seconds: int = 60

    # Path to the Athenaeum course catalog JSON. None → resolve the in-repo default.
    athenaeum_catalog_path: str | None = None

    # --- Groq (primary provider; tiers 1 & 2 of the Groq→Groq→Gemini→Gemini chain) ---
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model_workhorse: str = "openai/gpt-oss-120b"
    groq_model_fast: str = "openai/gpt-oss-20b"
    groq_model_reasoning: str = "openai/gpt-oss-120b"
    # gpt-oss reasons before answering; "low" keeps small classifier budgets from
    # being eaten by reasoning tokens (an empty visible answer).
    groq_reasoning_effort: str = "low"
    # Purpose-built prompt-injection/jailbreak classifier (returns a 0..1 score).
    groq_model_guard: str = "meta-llama/llama-prompt-guard-2-86m"
    # Block when the guard's jailbreak probability is at/above this.
    guard_block_threshold: float = 0.8

    # --- Google Gemini via AI Studio's OpenAI-compatible endpoint (tiers 3 & 4) ---
    gemini_api_key: str | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    gemini_model_workhorse: str = "gemini-2.5-flash"
    gemini_model_fast: str = "gemini-3.5-flash-lite"
    gemini_model_reasoning: str = "gemini-2.5-flash"

    # --- Live vector grounding: Cohere embeddings + Qdrant Cloud ---
    # When set, the course-grounding route runs hybrid retrieval (Qdrant vector search
    # fused with the lexical retriever). Unset, or Cohere's trial quota exhausted → the
    # deterministic lexical retriever answers alone, honestly labelled in the trace.
    cohere_api_key: str | None = None
    cohere_embed_model: str = "embed-v4.0"
    embed_dimensions: int = 1024
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    qdrant_collection: str = "athenaeum-courses"
    # Master toggle: off keeps the app on the lexical retriever even if keys are set.
    vector_search_live: bool = True
    # Cap the live retrieval so a slow call can't stall a turn (seconds).
    vector_search_timeout_seconds: float = 8.0

    # --- LLM-as-judge evaluation (groundedness / relevance / retrieval scoring) ---
    # Score each live grounded answer with an LLM judge on the 1..5 rubric
    # (Groundedness, Relevance, Retrieval). Drives the claim-support disclaimer and
    # surfaces scores in the trace. Off → the deterministic lexical groundedness proxy
    # stands in (offline / CI).
    evaluation_enabled: bool = True
    # Minimum groundedness score (1..5 rubric) for an answer to count as grounded;
    # below it the answer is treated as ungrounded and gets the honesty disclaimer even
    # when it cites a real module id. On the rubric 3 = "some claims unsupported" (a
    # partially-grounded C-minus that should NOT pass); 4 = "mostly/fully supported".
    # Default 4.0 so only a mostly/fully-supported answer clears the gate.
    groundedness_min_score: float = 4.0
    # The verdict gates on EVERY judge that produced a score, not groundedness alone.
    # Each threshold below is on the same 1..5 rubric and gates the verdict ONLY when
    # that judge actually scored — an absent/errored judge (no number) never blocks the
    # answer ("verification never blocks the answer"); a real low score does. Bias: these
    # only tighten the gate, never relax groundedness.
    # Relevance — does the answer address the question? Gates only when the judge scored.
    relevance_min_score: float = 3.0
    # Retrieval — was the cited context relevant/well-ranked? Gates only when it scored.
    retrieval_min_score: float = 3.0
    # Cap evaluation so a slow judge can't stall a turn (seconds).
    evaluation_timeout_seconds: float = 20.0

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
    def groq_configured(self) -> bool:
        """True when a usable Groq API key is present (the primary provider)."""
        return not _is_placeholder(self.groq_api_key)

    @property
    def gemini_configured(self) -> bool:
        """True when a usable Gemini API key is present (the fallback provider)."""
        return not _is_placeholder(self.gemini_api_key)

    @property
    def vector_search_configured(self) -> bool:
        """True only when Cohere + Qdrant credentials are all present."""
        return not any(
            _is_placeholder(v) for v in (self.cohere_api_key, self.qdrant_url, self.qdrant_api_key)
        )

    @property
    def vector_search_enabled(self) -> bool:
        """Live vector retrieval on the answer path: toggled on, configured, not offline.

        Gated by ``llm_offline`` so the zero-credential / forced-offline demo lane never
        makes a live call; the offline lexical retriever answers instead.
        """
        return self.vector_search_live and self.vector_search_configured and not self.llm_offline

    @property
    def evaluation_available(self) -> bool:
        """The LLM judge can score answers: enabled, a provider is configured, online."""
        return self.evaluation_enabled and not self.llm_offline

    @property
    def llm_offline(self) -> bool:
        """Use the deterministic offline LLM path when forced, or when NO provider is set.

        The agent pipeline can run on Groq *or* Gemini; it only drops to the
        deterministic mock when forced (``OFFLINE_LLM=true``) or when neither
        provider is configured (zero-credential demo / CI lane).
        """
        return self.offline_llm or not (self.groq_configured or self.gemini_configured)

    @property
    def grader_offline_demo(self) -> bool:
        """True ONLY for the explicit offline demo (``OFFLINE_LLM=true``).

        The grader's auto-pass stub (a fixed passing score) is a deliberate demo
        convenience, so it must fire only when offline is *explicitly* requested —
        NOT in the no-credentials case that ``llm_offline`` also covers. A deploy
        booted without any provider must never silently certify free-text answers;
        the grader treats that case as "cannot grade" and fails closed instead.
        """
        return self.offline_llm

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

    def require_gemini(self) -> GeminiConfig:
        """Return a validated GeminiConfig or raise loudly if the key is missing."""
        if _is_placeholder(self.gemini_api_key):
            raise RuntimeError("Gemini not configured — missing/placeholder: GEMINI_API_KEY")
        assert self.gemini_api_key is not None
        return GeminiConfig(
            api_key=self.gemini_api_key,
            base_url=self.gemini_base_url,
            model_workhorse=self.gemini_model_workhorse,
            model_fast=self.gemini_model_fast,
            model_reasoning=self.gemini_model_reasoning,
        )

    def require_chat_provider(self) -> ProviderConfig:
        """The first configured provider in chain order (Groq, then Gemini)."""
        if self.groq_configured:
            return self.require_groq()
        return self.require_gemini()

    def require_vector_search(self) -> VectorSearchConfig:
        """Return a validated VectorSearchConfig or raise loudly listing what is missing."""
        missing = [
            name
            for name, value in (
                ("COHERE_API_KEY", self.cohere_api_key),
                ("QDRANT_URL", self.qdrant_url),
                ("QDRANT_API_KEY", self.qdrant_api_key),
            )
            if _is_placeholder(value)
        ]
        if missing:
            raise RuntimeError("Vector search not configured — missing: " + ", ".join(missing))
        assert self.cohere_api_key is not None
        assert self.qdrant_url is not None
        assert self.qdrant_api_key is not None
        return VectorSearchConfig(
            cohere_api_key=self.cohere_api_key,
            embed_model=self.cohere_embed_model,
            embed_dimensions=self.embed_dimensions,
            qdrant_url=self.qdrant_url.rstrip("/"),
            qdrant_api_key=self.qdrant_api_key,
            collection=self.qdrant_collection,
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
