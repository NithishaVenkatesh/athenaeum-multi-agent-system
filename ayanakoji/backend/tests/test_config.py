"""Tests for settings parsing and the fail-loud Foundry config gate (offline)."""

from __future__ import annotations

import pytest
from app.config import (
    FoundryConfig,
    GroqConfig,
    SearchConfig,
    Settings,
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


# --- Foundry config gate ---------------------------------------------------


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


def test_foundry_not_configured_by_default() -> None:
    # No foundry fields set -> not configured.
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
    )
    assert settings.foundry_configured is False


def test_require_foundry_raises_listing_missing() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    with pytest.raises(RuntimeError) as exc:
        settings.require_foundry()
    message = str(exc.value)
    assert "FOUNDRY_PROJECT_ENDPOINT" in message
    assert "AZURE_OPENAI_ENDPOINT" in message
    assert "AZURE_OPENAI_API_KEY" in message


def test_require_foundry_returns_config_when_set() -> None:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        foundry_project_endpoint="https://r.services.ai.azure.com/api/projects/p",
        azure_openai_endpoint="https://r.openai.azure.com/",
        azure_openai_api_key="real-key-123",
    )
    assert settings.foundry_configured is True
    config = settings.require_foundry()
    assert isinstance(config, FoundryConfig)
    assert config.openai_endpoint == "https://r.openai.azure.com/"
    assert config.model_workhorse == "gpt-4o-mini"
    assert config.model_fast == "gpt-4o-mini"
    assert config.openai_api_version == "2024-10-21"


# --- Groq fallback config gate ---------------------------------------------


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
    assert config.model_workhorse == "llama-3.3-70b-versatile"
    assert config.model_fast == "llama-3.1-8b-instant"


def test_llm_offline_false_when_only_groq_configured() -> None:
    # The pipeline can run on Groq alone — not forced offline just because Azure is unset.
    # offline_llm=False explicitly overrides the autouse OFFLINE_LLM=true test fixture.
    settings = Settings(_env_file=None, groq_api_key="gsk_realkey", offline_llm=False)  # type: ignore[call-arg]
    assert settings.foundry_configured is False
    assert settings.llm_offline is False


def test_llm_offline_true_when_no_provider() -> None:
    settings = Settings(_env_file=None, offline_llm=False)  # type: ignore[call-arg]
    assert settings.llm_offline is True


def test_offline_forced_overrides_configured_providers() -> None:
    settings = Settings(_env_file=None, groq_api_key="gsk_realkey", offline_llm=True)  # type: ignore[call-arg]
    assert settings.llm_offline is True


# --- Azure AI Search / Foundry IQ knowledge base ---------------------------


def test_search_not_configured_by_default() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.search_configured is False
    with pytest.raises(RuntimeError) as exc:
        settings.require_search()
    message = str(exc.value)
    assert "SEARCH_ENDPOINT" in message
    assert "SEARCH_ADMIN_KEY" in message


def test_search_configured_and_require_returns_config() -> None:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        search_endpoint="https://athenaeum-search.search.windows.net",
        search_admin_key="real-admin-key",
    )
    assert settings.search_configured is True
    config = settings.require_search()
    assert isinstance(config, SearchConfig)
    assert config.endpoint == "https://athenaeum-search.search.windows.net"
    assert config.index_name == "athenaeum-courses"
    assert config.semantic_config == "athenaeum-semantic"
    assert config.knowledge_base_name == "athenaeum-knowledge-base"
    assert config.reasoning_effort == "low"


def test_search_placeholder_endpoint_is_not_configured() -> None:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        search_endpoint="<your-search-endpoint>",
        search_admin_key="real-admin-key",
    )
    assert settings.search_configured is False


def test_foundry_iq_enabled_requires_toggle_creds_and_online() -> None:
    base = {
        "search_endpoint": "https://s.search.windows.net",
        "search_admin_key": "real-admin-key",
        # an online provider so llm_offline is False
        "groq_api_key": "gsk_realkey",
        "offline_llm": False,
    }
    on = Settings(_env_file=None, **base)  # type: ignore[arg-type]
    assert on.foundry_iq_enabled is True

    # Forced offline → never make a live Search call, even when configured.
    off = Settings(_env_file=None, **{**base, "offline_llm": True})  # type: ignore[arg-type]
    assert off.foundry_iq_enabled is False

    # Toggle off keeps the app on the offline lexical retriever.
    toggled = Settings(_env_file=None, **{**base, "foundry_iq_live": False})  # type: ignore[arg-type]
    assert toggled.foundry_iq_enabled is False

    # No Search creds → disabled regardless of toggle.
    no_creds = Settings(_env_file=None, groq_api_key="gsk_realkey", offline_llm=False)  # type: ignore[call-arg]
    assert no_creds.foundry_iq_enabled is False


def test_evaluation_available_requires_aoai_and_online() -> None:
    aoai = {
        "foundry_project_endpoint": "https://r.services.ai.azure.com/api/projects/p",
        "azure_openai_endpoint": "https://r.openai.azure.com/",
        "azure_openai_api_key": "real-key-123",
    }
    on = Settings(_env_file=None, offline_llm=False, **aoai)  # type: ignore[arg-type]
    assert on.evaluation_available is True

    # Offline → no live evaluator calls.
    off = Settings(_env_file=None, offline_llm=True, **aoai)  # type: ignore[arg-type]
    assert off.evaluation_available is False

    # Groq-only (no AOAI judge) → evaluation can't run.
    groq_only = Settings(_env_file=None, groq_api_key="gsk_realkey", offline_llm=False)  # type: ignore[call-arg]
    assert groq_only.evaluation_available is False

    # Explicitly disabled.
    disabled = Settings(_env_file=None, evaluation_enabled=False, offline_llm=False, **aoai)  # type: ignore[arg-type]
    assert disabled.evaluation_available is False
