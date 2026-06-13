"""Model-router fallback-chain tests (offline; fake providers, no SDK/creds)."""

from __future__ import annotations

from collections.abc import Iterator, Sequence

import pytest
from app.agent.llm import (
    AllProvidersDown,
    Capability,
    ModelRouter,
    Provider,
    RawCompletion,
)
from app.config import Settings


class FakeProvider:
    """A scriptable provider: each call pops the next behaviour off ``script``."""

    def __init__(self, name: Provider, script: list[object]) -> None:
        self.name = name
        self._script = list(script)
        self.calls: list[tuple[str, str]] = []  # (kind, model)

    def _next(self, model: str, kind: str) -> object:
        self.calls.append((kind, model))
        behaviour = self._script.pop(0)
        if isinstance(behaviour, Exception):
            raise behaviour
        return behaviour

    def complete(
        self, model: str, messages: Sequence[dict[str, str]], *, json_mode: bool, max_tokens: int
    ) -> RawCompletion:
        result = self._next(model, "complete")
        assert isinstance(result, RawCompletion)
        return result

    def stream(
        self, model: str, messages: Sequence[dict[str, str]], *, max_tokens: int
    ) -> Iterator[str]:
        result = self._next(model, "stream")
        assert isinstance(result, list)
        return iter(result)


def _settings() -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        foundry_project_endpoint="https://r.services.ai.azure.com/api/projects/p",
        azure_openai_endpoint="https://r.openai.azure.com/",
        azure_openai_api_key="real-key",
        groq_api_key="gsk_real",
    )


def test_chain_orders_azure_then_groq_with_tiers() -> None:
    azure = FakeProvider(Provider.AZURE, [])
    groq = FakeProvider(Provider.GROQ, [])
    router = ModelRouter(_settings(), azure=azure, groq=groq)
    chain = router.chain(Capability.FAST)
    tiers = [(a.provider, a.tier) for _, a in chain]
    assert tiers == [
        (Provider.AZURE, 1),
        (Provider.AZURE, 2),
        (Provider.GROQ, 3),
        (Provider.GROQ, 4),
    ]


def test_complete_returns_first_success_tier1() -> None:
    azure = FakeProvider(Provider.AZURE, [RawCompletion(text="ok", completion_tokens=3)])
    groq = FakeProvider(Provider.GROQ, [])
    router = ModelRouter(_settings(), azure=azure, groq=groq)
    result = router.complete(Capability.WORKHORSE, [{"role": "user", "content": "hi"}])
    assert result.text == "ok"
    assert result.provider is Provider.AZURE
    assert result.tier == 1
    assert result.completion_tokens == 3
    assert groq.calls == []  # never reached


def test_complete_falls_through_to_groq() -> None:
    # Both Azure rungs fail, first Groq rung wins at tier 3.
    azure = FakeProvider(Provider.AZURE, [RuntimeError("429"), RuntimeError("500")])
    groq = FakeProvider(Provider.GROQ, [RawCompletion(text="groq-answer")])
    router = ModelRouter(_settings(), azure=azure, groq=groq)
    result = router.complete(Capability.WORKHORSE, [{"role": "user", "content": "hi"}])
    assert result.text == "groq-answer"
    assert result.provider is Provider.GROQ
    assert result.tier == 3
    assert len(azure.calls) == 2


def test_all_providers_down_raises() -> None:
    azure = FakeProvider(Provider.AZURE, [RuntimeError("x"), RuntimeError("x")])
    groq = FakeProvider(Provider.GROQ, [RuntimeError("x"), RuntimeError("x")])
    router = ModelRouter(_settings(), azure=azure, groq=groq)
    with pytest.raises(AllProvidersDown):
        router.complete(Capability.FAST, [{"role": "user", "content": "hi"}])


def test_complete_no_provider_configured_raises() -> None:
    settings = Settings(_env_file=None, offline_llm=False)  # type: ignore[call-arg]
    router = ModelRouter(settings)
    with pytest.raises(AllProvidersDown):
        router.complete(Capability.FAST, [{"role": "user", "content": "hi"}])


def test_stream_yields_tokens_and_reattaches_first() -> None:
    azure = FakeProvider(Provider.AZURE, [["Hel", "lo", " world"]])
    groq = FakeProvider(Provider.GROQ, [])
    router = ModelRouter(_settings(), azure=azure, groq=groq)
    handle = router.stream(Capability.WORKHORSE, [{"role": "user", "content": "hi"}])
    assert handle.tier == 1
    assert "".join(handle.tokens) == "Hello world"


def test_stream_falls_through_on_pre_token_failure() -> None:
    azure = FakeProvider(Provider.AZURE, [RuntimeError("stream boom"), RuntimeError("again")])
    groq = FakeProvider(Provider.GROQ, [["from", "-groq"]])
    router = ModelRouter(_settings(), azure=azure, groq=groq)
    handle = router.stream(Capability.WORKHORSE, [{"role": "user", "content": "hi"}])
    assert handle.provider is Provider.GROQ
    assert handle.tier == 3
    assert "".join(handle.tokens) == "from-groq"


def test_stream_empty_stream_degrades() -> None:
    azure = FakeProvider(Provider.AZURE, [[], []])  # both Azure rungs empty
    groq = FakeProvider(Provider.GROQ, [["ok"]])
    router = ModelRouter(_settings(), azure=azure, groq=groq)
    handle = router.stream(Capability.WORKHORSE, [{"role": "user", "content": "hi"}])
    assert handle.provider is Provider.GROQ
    assert "".join(handle.tokens) == "ok"


def test_groq_only_when_azure_unconfigured() -> None:
    settings = Settings(_env_file=None, groq_api_key="gsk_real", offline_llm=False)  # type: ignore[call-arg]
    groq = FakeProvider(Provider.GROQ, [RawCompletion(text="g")])
    router = ModelRouter(settings, groq=groq)
    chain = router.chain(Capability.WORKHORSE)
    assert all(a.provider is Provider.GROQ for _, a in chain)
    assert [a.tier for _, a in chain] == [1, 2]
    result = router.complete(Capability.WORKHORSE, [{"role": "user", "content": "hi"}])
    assert result.provider is Provider.GROQ and result.tier == 1
