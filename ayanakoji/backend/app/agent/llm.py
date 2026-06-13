"""Model router with an explicit Azure → Azure → Groq → Groq fallback chain.

Per-agent model choice is by *capability* (a cheap classifier for routing, a
workhorse for grounded prose), not a single global model. Each capability maps
to an ordered list of attempts across two providers; the router walks the chain
and returns the first success, recording which **tier** answered (1=Azure
primary, 2=Azure fallback, 3=Groq primary, 4=Groq fallback) for the telemetry
the user sees as a grounding source.

If every configured provider fails, the router raises :class:`AllProvidersDown`
so the orchestrator can surface an explicit "services are down" message — never
a silent failure. The deterministic *offline* path is owned by each agent (see
``settings.llm_offline``), mirroring ``app/courses/service.py``; this module is
only ever exercised when a real provider is configured.

SDK imports are lazy (inside the provider classes) so the module imports cleanly
in the offline CI lane where ``openai`` is not installed.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

# A chat message in the OpenAI ``{role, content}`` shape.
Message = dict[str, str]


class Capability(StrEnum):
    """What an agent needs from a model — drives which deployments are tried."""

    FAST = "fast"  # cheap, low-latency classify (router, injection gate)
    WORKHORSE = "workhorse"  # grounded prose / narration (answers)
    REASONING = "reasoning"  # deep reasoning (not on the chat hot path)


class Provider(StrEnum):
    AZURE = "azure"
    GROQ = "groq"


class LLMError(RuntimeError):
    """Base for model-routing failures."""


class AllProvidersDown(LLMError):
    """Every configured provider in the chain failed — the final, explicit fallback."""


@dataclass(frozen=True)
class Attempt:
    """One rung of the fallback chain: which provider+model to try, at which tier."""

    provider: Provider
    model: str
    tier: int


@dataclass(frozen=True)
class RawCompletion:
    """A provider's raw, non-streamed reply plus its token accounting."""

    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(frozen=True)
class LLMResult:
    """A completed model call, tagged with the tier that answered (for telemetry)."""

    text: str
    provider: Provider
    model: str
    tier: int
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int


@dataclass(frozen=True)
class StreamHandle:
    """A live token stream from the first provider that answered, plus its tier tag."""

    tokens: Iterator[str]
    provider: Provider
    model: str
    tier: int


def _is_reasoning_model(model: str) -> bool:
    """o-series reasoning deployments take ``developer`` role + no temperature (§26)."""
    head = model.lower()
    return head.startswith(("o1", "o3", "o4")) or head.startswith("o-")


class CompletionProvider(Protocol):
    """Minimal provider surface the router depends on (Azure/Groq/fakes implement it)."""

    name: Provider

    def complete(
        self, model: str, messages: Sequence[Message], *, json_mode: bool, max_tokens: int
    ) -> RawCompletion: ...

    def stream(
        self, model: str, messages: Sequence[Message], *, max_tokens: int
    ) -> Iterator[str]: ...


# ── Real providers (lazy SDK import; only constructed when configured) ─────────


class _OpenAICompatibleProvider:
    """Shared impl for Azure OpenAI and Groq (both speak the OpenAI chat API)."""

    name: Provider

    def __init__(self, client: Any, *, is_azure: bool) -> None:
        self._client = client
        self._is_azure = is_azure

    def _kwargs(self, model: str, max_tokens: int) -> dict[str, Any]:
        # o-series (Azure) reject temperature/top_p and rename the token budget.
        if self._is_azure and _is_reasoning_model(model):
            return {"max_completion_tokens": max_tokens}
        return {"max_tokens": max_tokens, "temperature": 0.3}

    def _project_messages(self, model: str, messages: Sequence[Message]) -> list[Message]:
        if self._is_azure and _is_reasoning_model(model):
            return [
                {**m, "role": "developer"} if m.get("role") == "system" else dict(m)
                for m in messages
            ]
        return [dict(m) for m in messages]

    def complete(
        self, model: str, messages: Sequence[Message], *, json_mode: bool, max_tokens: int
    ) -> RawCompletion:
        kwargs = self._kwargs(model, max_tokens)
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = self._client.chat.completions.create(
            model=model,
            messages=self._project_messages(model, messages),
            **kwargs,
        )
        text = (response.choices[0].message.content or "").strip()
        usage = getattr(response, "usage", None)
        return RawCompletion(
            text=text,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )

    def stream(self, model: str, messages: Sequence[Message], *, max_tokens: int) -> Iterator[str]:
        kwargs = self._kwargs(model, max_tokens)
        stream = self._client.chat.completions.create(
            model=model,
            messages=self._project_messages(model, messages),
            stream=True,
            **kwargs,
        )
        for chunk in stream:
            choices = getattr(chunk, "choices", None)
            if not choices:
                continue
            token = getattr(choices[0].delta, "content", None)
            if token:
                yield token


def _build_azure_provider(settings: Settings) -> _OpenAICompatibleProvider:
    from app.foundry import build_openai_client

    provider = _OpenAICompatibleProvider(
        build_openai_client(settings.require_foundry()), is_azure=True
    )
    provider.name = Provider.AZURE
    return provider


def _build_groq_provider(settings: Settings) -> _OpenAICompatibleProvider:
    from openai import OpenAI

    config = settings.require_groq()
    client = OpenAI(api_key=config.api_key, base_url=config.base_url)
    provider = _OpenAICompatibleProvider(client, is_azure=False)
    provider.name = Provider.GROQ
    return provider


# ── Router ─────────────────────────────────────────────────────────────────────


class ModelRouter:
    """Walks the Azure→Azure→Groq→Groq chain for a capability; first success wins."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        azure: CompletionProvider | None = None,
        groq: CompletionProvider | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        # Providers are lazily built on first use unless injected (tests inject fakes).
        self._azure = azure
        self._groq = groq
        self._azure_built = azure is not None
        self._groq_built = groq is not None

    # -- provider resolution ----------------------------------------------------

    def _azure_provider(self) -> CompletionProvider | None:
        if not self._azure_built:
            self._azure_built = True
            if self._settings.foundry_configured:
                try:
                    self._azure = _build_azure_provider(self._settings)
                except Exception as exc:  # noqa: BLE001 — degrade to next provider
                    logger.warning("Azure provider unavailable: %s", exc)
        return self._azure

    def _groq_provider(self) -> CompletionProvider | None:
        if not self._groq_built:
            self._groq_built = True
            if self._settings.groq_configured:
                try:
                    self._groq = _build_groq_provider(self._settings)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Groq provider unavailable: %s", exc)
        return self._groq

    # -- chain construction -----------------------------------------------------

    def _azure_models(self, capability: Capability) -> list[str]:
        s = self._settings
        primary = {
            Capability.FAST: s.model_fast,
            Capability.WORKHORSE: s.model_workhorse,
            Capability.REASONING: s.model_reasoning,
        }[capability]
        # Fallback to the robust general workhorse (a retry when already workhorse).
        return [primary, s.model_workhorse]

    def _groq_models(self, capability: Capability) -> list[str]:
        s = self._settings
        primary = {
            Capability.FAST: s.groq_model_fast,
            Capability.WORKHORSE: s.groq_model_workhorse,
            Capability.REASONING: s.groq_model_reasoning,
        }[capability]
        secondary = (
            s.groq_model_fast if capability is Capability.WORKHORSE else s.groq_model_workhorse
        )
        return [primary, secondary]

    def chain(self, capability: Capability) -> list[tuple[CompletionProvider, Attempt]]:
        """Ordered (provider, attempt) rungs for a capability, configured-only."""
        rungs: list[tuple[CompletionProvider, Attempt]] = []
        tier = 0
        azure = self._azure_provider()
        if azure is not None:
            for model in self._azure_models(capability):
                tier += 1
                rungs.append((azure, Attempt(Provider.AZURE, model, tier)))
        groq = self._groq_provider()
        if groq is not None:
            for model in self._groq_models(capability):
                tier += 1
                rungs.append((groq, Attempt(Provider.GROQ, model, tier)))
        return rungs

    # -- calls ------------------------------------------------------------------

    def complete(
        self,
        capability: Capability,
        messages: Sequence[Message],
        *,
        json_mode: bool = False,
        max_tokens: int = 512,
    ) -> LLMResult:
        """Non-streaming completion; tries each rung until one succeeds."""
        rungs = self.chain(capability)
        if not rungs:
            raise AllProvidersDown("no LLM provider configured")
        last: Exception | None = None
        for provider, attempt in rungs:
            started = time.monotonic()
            try:
                raw = provider.complete(
                    attempt.model, messages, json_mode=json_mode, max_tokens=max_tokens
                )
            except Exception as exc:  # noqa: BLE001 — record and try the next rung
                logger.warning(
                    "tier %d %s/%s failed: %s", attempt.tier, attempt.provider, attempt.model, exc
                )
                last = exc
                continue
            return LLMResult(
                text=raw.text,
                provider=attempt.provider,
                model=attempt.model,
                tier=attempt.tier,
                prompt_tokens=raw.prompt_tokens,
                completion_tokens=raw.completion_tokens,
                latency_ms=int((time.monotonic() - started) * 1000),
            )
        raise AllProvidersDown(f"all {len(rungs)} provider tiers failed") from last

    def stream(
        self,
        capability: Capability,
        messages: Sequence[Message],
        *,
        max_tokens: int = 1024,
    ) -> StreamHandle:
        """Open a token stream from the first rung that yields a first token.

        Falling back mid-stream is impossible, so a rung must produce its first
        token to "win"; failures before the first token degrade to the next rung.
        """
        rungs = self.chain(capability)
        if not rungs:
            raise AllProvidersDown("no LLM provider configured")
        last: Exception | None = None
        for provider, attempt in rungs:
            try:
                iterator = provider.stream(attempt.model, messages, max_tokens=max_tokens)
                first = next(iterator)
            except StopIteration:
                # Empty stream — treat as a failure and try the next rung.
                last = LLMError(f"tier {attempt.tier} produced no tokens")
                continue
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "tier %d %s/%s stream failed: %s",
                    attempt.tier,
                    attempt.provider,
                    attempt.model,
                    exc,
                )
                last = exc
                continue
            return StreamHandle(
                tokens=_prepend(first, iterator),
                provider=attempt.provider,
                model=attempt.model,
                tier=attempt.tier,
            )
        raise AllProvidersDown(f"all {len(rungs)} provider tiers failed") from last


def _prepend(first: str, rest: Iterator[str]) -> Iterator[str]:
    """Re-attach the peeked first token to the front of a stream."""
    yield first
    yield from rest
