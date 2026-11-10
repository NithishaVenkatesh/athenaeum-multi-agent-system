"""Tests for settings parsing and the fail-loud provider config gates (offline)."""

from __future__ import annotations

import pytest
from app.config import (
    GeminiConfig,
    GroqConfig,
    Settings,
    VectorSearchConfig,
    _is_placeholder,
    get_settings,
)


def test_defaults() -> None:
    settings = Settings()
    assert settings.app_name == "athenaeum-backend"
    assert settings.environment == "development"


def test_cors_origin_list_splits_and_trims() -> None:
    settings = Settings(cors_origins="http://localhost:3000, https://example.com ,")
    assert settings.cors_origin_list == ["http://localhost:3000", "https://example.com"]


def test_get_settings_returns_settings() -> None:
    assert isinstance(get_settings(), Settings)


# --- Placeholder detection ---------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, True),
        ("", True),
        ("   ", True),
        ("<your-endpoint>", True),
        ("TODO", True),
        ("changeme", True),
        ("your-key", True),
        ("https://real.openai.azure.com/", False),
        ("sk-realkey", False),
    ],
)
def test_is_placeholder(value: str | None, expected: bool) -> None:
    assert _is_placeholder(value) is expected


def test_gemini_not_configured_by_default() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.gemini_configured is False
    with pytest.raises(RuntimeError) as exc:
        settings.require_gemini()
    assert "GEMINI_API_KEY" in str(exc.value)


def test_gemini_configured_and_require_returns_config() -> None:
    settings = Settings(_env_file=None, gemini_api_key="real-gemini-key")  # type: ignore[call-arg]
    assert settings.gemini_configured is True
    config = settings.require_gemini()
    assert isinstance(config, GeminiConfig)
    assert config.base_url == "https://generativelanguage.googleapis.com/v1beta/openai/"
    assert config.model_workhorse == "gemini-2.5-flash"
    assert config.model_fast == "gemini-3.5-flash-lite"


def test_require_chat_provider_prefers_groq_then_gemini() -> None:
    both = Settings(_env_file=None, groq_api_key="gsk_x", gemini_api_key="gm_x")  # type: ignore[call-arg]
    assert both.require_chat_provider().base_url == "https://api.groq.com/openai/v1"
    gemini_only = Settings(_env_file=None, gemini_api_key="gm_x")  # type: ignore[call-arg]
    assert "generativelanguage" in gemini_only.require_chat_provider().base_url


# --- Groq primary config gate ---------------------------------------------


def test_groq_not_configured_by_default() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.groq_configured is False
    with pytest.raises(RuntimeError) as exc:
        settings.require_groq()
    assert "GROQ_API_KEY" in str(exc.value)


def test_groq_configured_and_require_returns_config() -> None:
    settings = Settings(_env_file=None, groq_api_key="gsk_realkey")  # type: ignore[call-arg]
    assert settings.groq_configured is True
    config = settings.require_groq()
    assert isinstance(config, GroqConfig)
    assert config.base_url == "https://api.groq.com/openai/v1"
    assert config.model_workhorse == "openai/gpt-oss-120b"
    assert config.model_fast == "openai/gpt-oss-20b"


def test_llm_offline_false_when_only_groq_configured() -> None:
    # The pipeline can run on Groq alone — not forced offline just because Gemini is unset.
    # offline_llm=False explicitly overrides the autouse OFFLINE_LLM=true test fixture.
    settings = Settings(_env_file=None, groq_api_key="gsk_realkey", offline_llm=False)  # type: ignore[call-arg]
    assert settings.gemini_configured is False
    assert settings.llm_offline is False


def test_llm_offline_false_when_only_gemini_configured() -> None:
    settings = Settings(_env_file=None, gemini_api_key="gm_realkey", offline_llm=False)  # type: ignore[call-arg]
    assert settings.llm_offline is False


def test_llm_offline_true_when_no_provider() -> None:
    settings = Settings(_env_file=None, offline_llm=False)  # type: ignore[call-arg]
    assert settings.llm_offline is True


def test_offline_forced_overrides_configured_providers() -> None:
    settings = Settings(_env_file=None, groq_api_key="gsk_realkey", offline_llm=True)  # type: ignore[call-arg]
    assert settings.llm_offline is True


def test_grader_offline_demo_only_for_explicit_offline() -> None:
    # Explicit demo: OFFLINE_LLM=true → demo stub allowed.
    demo = Settings(_env_file=None, offline_llm=True)  # type: ignore[call-arg]
    assert demo.grader_offline_demo is True

    # No provider but NOT an explicit demo: llm_offline is True yet the grader must
    # NOT treat this as the demo (it fails closed instead of auto-passing).
    no_creds = Settings(_env_file=None, offline_llm=False)  # type: ignore[call-arg]
    assert no_creds.llm_offline is True
    assert no_creds.grader_offline_demo is False


def test_groundedness_min_score_default_is_four() -> None:
    # Raised from 3.0 (a C-minus "some claims unsupported") to 4.0 (mostly/fully supported).
    assert Settings(_env_file=None).groundedness_min_score == 4.0  # type: ignore[call-arg]


# --- Live vector search (Cohere + Qdrant) ---------------------------------


_VECTOR = {
    "cohere_api_key": "real-cohere-key",
    "qdrant_url": "https://cluster.cloud.qdrant.io/",
    "qdrant_api_key": "real-qdrant-key",
}


def test_vector_search_not_configured_by_default() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.vector_search_configured is False
    with pytest.raises(RuntimeError) as exc:
        settings.require_vector_search()
    message = str(exc.value)
    for name in ("COHERE_API_KEY", "QDRANT_URL", "QDRANT_API_KEY"):
        assert name in message


def test_vector_search_configured_and_require_returns_config() -> None:
    settings = Settings(_env_file=None, **_VECTOR)  # type: ignore[arg-type]
    assert settings.vector_search_configured is True
    config = settings.require_vector_search()
    assert isinstance(config, VectorSearchConfig)
    assert config.qdrant_url == "https://cluster.cloud.qdrant.io"  # trailing slash stripped
    assert config.collection == "athenaeum-courses"
    assert config.embed_model == "embed-v4.0"
    assert config.embed_dimensions == 1024


def test_vector_search_placeholder_is_not_configured() -> None:
    settings = Settings(_env_file=None, **{**_VECTOR, "qdrant_url": "<your-cluster>"})  # type: ignore[arg-type]
    assert settings.vector_search_configured is False


def test_vector_search_enabled_requires_toggle_creds_and_online() -> None:
    base = {**_VECTOR, "groq_api_key": "gsk_realkey", "offline_llm": False}
    on = Settings(_env_file=None, **base)  # type: ignore[arg-type]
    assert on.vector_search_enabled is True

    # Forced offline → never make a live call, even when configured.
    off = Settings(_env_file=None, **{**base, "offline_llm": True})  # type: ignore[arg-type]
    assert off.vector_search_enabled is False

    # Toggle off keeps the app on the offline lexical retriever.
    toggled = Settings(_env_file=None, **{**base, "vector_search_live": False})  # type: ignore[arg-type]
    assert toggled.vector_search_enabled is False

    # No vector creds → disabled regardless of toggle.
    no_creds = Settings(_env_file=None, groq_api_key="gsk_realkey", offline_llm=False)  # type: ignore[call-arg]
    assert no_creds.vector_search_enabled is False


def test_evaluation_available_requires_provider_and_online() -> None:
    on = Settings(_env_file=None, offline_llm=False, groq_api_key="gsk_realkey")  # type: ignore[call-arg]
    assert on.evaluation_available is True

    # Offline → no live judge calls.
    off = Settings(_env_file=None, offline_llm=True, groq_api_key="gsk_realkey")  # type: ignore[call-arg]
    assert off.evaluation_available is False

    # No provider at all → offline → no judge.
    none = Settings(_env_file=None, offline_llm=False)  # type: ignore[call-arg]
    assert none.evaluation_available is False

    # Explicitly disabled.
    disabled = Settings(
        _env_file=None,  # type: ignore[call-arg]
        evaluation_enabled=False,
        offline_llm=False,
        groq_api_key="gsk_realkey",
    )
    assert disabled.evaluation_available is False
