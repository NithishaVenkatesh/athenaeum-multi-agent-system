"""Tests for settings parsing."""

from __future__ import annotations

from app.config import Settings, get_settings


def test_defaults() -> None:
    settings = Settings()
    assert settings.app_name == "ayanakoji-backend"
    assert settings.environment == "development"


def test_cors_origin_list_splits_and_trims() -> None:
    settings = Settings(cors_origins="http://localhost:3000, https://example.com ,")
    assert settings.cors_origin_list == ["http://localhost:3000", "https://example.com"]


def test_get_settings_returns_settings() -> None:
    assert isinstance(get_settings(), Settings)
