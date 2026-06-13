"""Chat title + streaming reply service — offline fallback and live (faked) paths."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.config import FoundryConfig, Settings
from app.courses.service import generate_title, stream_reply


def _offline_settings() -> Settings:
    return Settings(offline_llm=True)


def _live_settings() -> Settings:
    # Explicit init kwargs beat the autouse OFFLINE_LLM env var, so the live path runs.
    return Settings(
        offline_llm=False,
        foundry_project_endpoint="https://proj.services.ai.azure.com/api/projects/p",
        azure_openai_endpoint="https://res.openai.azure.com/",
        azure_openai_api_key="sk-test-key",
    )


# ── Offline path ────────────────────────────────────────────────────────────


def test_offline_title_uses_first_words_of_message() -> None:
    title = generate_title(
        "How do Azure Functions triggers and bindings actually work end to end?",
        settings=_offline_settings(),
    )
    assert title == "How do Azure Functions triggers and"  # first six words


def test_offline_title_handles_blank_message() -> None:
    assert generate_title("   ", settings=_offline_settings()) == "New chat"


def test_offline_title_caps_overly_long_titles() -> None:
    long_words = (
        "authentication authorization configuration orchestration observability instrumentation"
    )
    title = generate_title(long_words, settings=_offline_settings())
    assert 0 < len(title) <= 48


def test_offline_stream_echoes_last_user_message() -> None:
    messages = [{"role": "user", "content": "Explain CI/CD pipelines"}]
    out = "".join(stream_reply(messages, settings=_offline_settings()))
    assert "offline mode" in out
    assert "Explain CI/CD pipelines" in out


# ── Live path (injected fake client) ──────────────────────────────────────────


def _resp(content: str | None) -> Any:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _chunk(content: str | None = None, *, empty: bool = False) -> Any:
    choices = [] if empty else [SimpleNamespace(delta=SimpleNamespace(content=content))]
    return SimpleNamespace(choices=choices)


class _Completions:
    def create(self, **kwargs: Any) -> Any:
        if kwargs.get("stream"):
            # An empty-choices chunk and a None token must both be skipped.
            return iter([_chunk(empty=True), _chunk("Hello"), _chunk(" there"), _chunk(None)])
        return _resp("Azure Functions Basics")


def _factory(config: FoundryConfig) -> Any:
    return SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))


def test_live_title_uses_model_response() -> None:
    title = generate_title(
        "How do triggers work?", settings=_live_settings(), client_factory=_factory
    )
    assert title == "Azure Functions Basics"


def test_live_title_falls_back_when_model_returns_blank() -> None:
    def blank_factory(config: FoundryConfig) -> Any:
        completions = SimpleNamespace(create=lambda **kw: _resp("   "))
        return SimpleNamespace(chat=SimpleNamespace(completions=completions))

    title = generate_title(
        "Explain blob storage tiers", settings=_live_settings(), client_factory=blank_factory
    )
    assert title == "Explain blob storage tiers"


def test_live_stream_yields_content_tokens_only() -> None:
    messages = [{"role": "user", "content": "hi"}]
    tokens = list(stream_reply(messages, settings=_live_settings(), client_factory=_factory))
    assert tokens == ["Hello", " there"]  # empty-choices chunk and None token skipped
