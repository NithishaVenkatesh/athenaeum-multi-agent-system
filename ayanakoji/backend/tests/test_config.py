"""Tests for settings parsing and the fail-loud Foundry config gate (offline)."""

from __future__ import annotations

import pytest
from app.config import FoundryConfig, Settings, _is_placeholder, get_settings


def test_defaults() -> None:
    settings = Settings()
    assert settings.app_name == "ayanakoji-backend"
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
    assert config.openai_api_version == "2024-10-21"
