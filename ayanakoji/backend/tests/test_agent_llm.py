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

    def complete_tools(self, *a: object, **k: object) -> tuple[str, list[object]]:  # pragma: no cover
        raise AssertionError("FakeProvider has no scripted tool calls")


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


class FakeToolProvider:
    """Scriptable tool-calling provider: each complete_tools call pops the next
    (text, tool_calls) tuple off the script."""

    def __init__(self, name: Provider, script: list[tuple[str, list[object]]]) -> None:
        self.name = name
        self._script = list(script)
        self.seen_messages: list[list[dict[str, object]]] = []

    def complete(self, *a: object, **k: object) -> RawCompletion:  # pragma: no cover
        raise AssertionError("not used")

    def stream(self, *a: object, **k: object):  # pragma: no cover
        raise AssertionError("not used")

    def complete_tools(self, model, messages, *, tools, tool_choice, max_tokens):  # type: ignore[no-untyped-def]
        self.seen_messages.append(list(messages))
        text, calls = self._script.pop(0)
        return text, calls


def test_run_tools_executes_handler_and_returns_final_text() -> None:
    from app.agent.llm import ToolCall

    azure = FakeToolProvider(
        Provider.AZURE,
        [
            ("", [ToolCall(id="c1", name="propose_plan", arguments='{"pace": "faster"}')]),
            ("Here is your faster plan.", []),
        ],
    )
    router = ModelRouter(_settings(), azure=azure, groq=FakeProvider(Provider.GROQ, []))
    captured: dict[str, object] = {}

    def propose_plan(args: dict[str, object]) -> dict[str, object]:
        captured.update(args)
        return {"weeks": 3}

    result = router.run_tools(
        Capability.WORKHORSE,
        [{"role": "user", "content": "make it faster"}],
        tools=[{"type": "function", "function": {"name": "propose_plan"}}],
        handlers={"propose_plan": propose_plan},
    )
    assert result.text == "Here is your faster plan."
    assert result.tier == 1
    assert result.rounds == 2
    assert captured == {"pace": "faster"}  # handler saw the model's parsed args
    # The tool result was fed back into the conversation for the second call.
    second_call_roles = [m["role"] for m in azure.seen_messages[1]]
    assert "tool" in second_call_roles


def test_run_tools_unknown_tool_is_reported_not_crashed() -> None:
    from app.agent.llm import ToolCall

    azure = FakeToolProvider(
        Provider.AZURE,
        [
            ("", [ToolCall(id="c1", name="does_not_exist", arguments="{}")]),
            ("Recovered.", []),
        ],
    )
    router = ModelRouter(_settings(), azure=azure, groq=FakeProvider(Provider.GROQ, []))
    result = router.run_tools(
        Capability.WORKHORSE,
        [{"role": "user", "content": "hi"}],
        tools=[],
        handlers={},
    )
    assert result.text == "Recovered."


class _Transient(Exception):
    """A retryable error (carries an HTTP-ish status code)."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"transient {status_code}")
        self.status_code = status_code


def test_retry_recovers_a_transient_blip_on_the_same_rung() -> None:
    # Azure rung 1 hits a 429 then succeeds on retry — it never falls to Groq.
    azure = FakeProvider(
        Provider.AZURE, [_Transient(429), RawCompletion(text="recovered")]
    )
    groq = FakeProvider(Provider.GROQ, [])
    router = ModelRouter(_settings(), azure=azure, groq=groq, sleep=lambda _s: None)
    result = router.complete(Capability.FAST, [{"role": "user", "content": "hi"}])
    assert result.text == "recovered"
    assert result.provider is Provider.AZURE
    assert result.tier == 1  # same rung, recovered via retry
    assert len(azure.calls) == 2  # one failed attempt + one success
    assert groq.calls == []


def test_non_transient_error_is_not_retried() -> None:
    # A plain error is not retryable: one attempt per rung, then fall through.
    azure = FakeProvider(Provider.AZURE, [RuntimeError("bad model"), RuntimeError("bad model")])
    groq = FakeProvider(Provider.GROQ, [RawCompletion(text="g")])
    router = ModelRouter(_settings(), azure=azure, groq=groq, sleep=lambda _s: None)
    result = router.complete(Capability.FAST, [{"role": "user", "content": "hi"}])
    assert result.provider is Provider.GROQ
    assert len(azure.calls) == 2  # NOT retried — one call per rung


def test_open_circuit_skips_a_dead_provider() -> None:
    from app.agent.llm import CircuitBreaker

    clock = {"t": 0.0}
    breaker = CircuitBreaker(threshold=2, cooldown=60.0, monotonic=lambda: clock["t"])
    # Two failed Azure rungs (one turn) cross the threshold and open Azure's circuit.
    azure = FakeProvider(Provider.AZURE, [RuntimeError("x"), RuntimeError("x")])
    groq = FakeProvider(Provider.GROQ, [RawCompletion(text="g1")])
    router = ModelRouter(
        _settings(), azure=azure, groq=groq, breaker=breaker, sleep=lambda _s: None
    )
    assert router.complete(Capability.FAST, [{"role": "user", "content": "1"}]).provider is (
        Provider.GROQ
    )
    assert len(azure.calls) == 2  # both Azure rungs tried this turn

    # Next turn: Azure's circuit is open → its rungs are skipped entirely.
    azure2 = FakeProvider(Provider.AZURE, [RawCompletion(text="should-not-run")])
    groq2 = FakeProvider(Provider.GROQ, [RawCompletion(text="g2")])
    router2 = ModelRouter(
        _settings(), azure=azure2, groq=groq2, breaker=breaker, sleep=lambda _s: None
    )
    result = router2.complete(Capability.FAST, [{"role": "user", "content": "2"}])
    assert result.provider is Provider.GROQ
    assert azure2.calls == []  # Azure skipped — no timeout paid

    # After the cooldown elapses the circuit half-opens and Azure is tried again.
    clock["t"] = 120.0
    azure3 = FakeProvider(Provider.AZURE, [RawCompletion(text="azure-back")])
    router3 = ModelRouter(
        _settings(), azure=azure3, groq=FakeProvider(Provider.GROQ, []), breaker=breaker,
        sleep=lambda _s: None,
    )
    assert router3.complete(Capability.FAST, [{"role": "user", "content": "3"}]).text == (
        "azure-back"
    )


def test_groq_only_when_azure_unconfigured() -> None:
    settings = Settings(_env_file=None, groq_api_key="gsk_real", offline_llm=False)  # type: ignore[call-arg]
    groq = FakeProvider(Provider.GROQ, [RawCompletion(text="g")])
    router = ModelRouter(settings, groq=groq)
    chain = router.chain(Capability.WORKHORSE)
    assert all(a.provider is Provider.GROQ for _, a in chain)
    assert [a.tier for _, a in chain] == [1, 2]
    result = router.complete(Capability.WORKHORSE, [{"role": "user", "content": "hi"}])
    assert result.provider is Provider.GROQ and result.tier == 1
