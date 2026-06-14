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

import json
import logging
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from enum import StrEnum
from functools import partial
from typing import Any, Protocol

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

# A chat message in the OpenAI ``{role, content}`` shape.
Message = dict[str, str]

# --- Resilience: retry transient blips, and a circuit breaker so a dead provider
# is skipped instead of paying its full timeout on every turn (critique M6) ---
RETRY_MAX_ATTEMPTS = 3  # total attempts on one rung before falling to the next
RETRY_BACKOFF_BASE_SECONDS = 0.25  # exponential: 0.25, 0.5, 1.0 ...
CIRCUIT_FAILURE_THRESHOLD = 4  # consecutive failures before a provider's circuit opens
CIRCUIT_COOLDOWN_SECONDS = 60.0  # how long an open circuit stays open before a retry
# HTTP statuses worth retrying (rate limit, timeout, transient server errors).
_RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
_RETRYABLE_EXC_NAMES = frozenset(
    {
        "RateLimitError",
        "APITimeoutError",
        "APIConnectionError",
        "InternalServerError",
        "ServiceUnavailableError",
    }
)


def _is_transient(exc: BaseException) -> bool:
    """True for errors worth retrying the *same* rung (rate limit, timeout, 5xx).

    A non-transient error (bad model name, auth, malformed request) falls straight
    through to the next rung — retrying it would only waste time. A content-filter
    rejection is a deterministic safety verdict, never transient: retrying the same
    prompt on the same provider will be filtered identically, so we never burn the
    retry budget on it.
    """
    if _is_content_filter(exc):
        return False
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    status = getattr(exc, "status_code", None)
    if not isinstance(status, int):
        status = getattr(exc, "status", None)
    if isinstance(status, int) and status in _RETRYABLE_STATUS:
        return True
    return type(exc).__name__ in _RETRYABLE_EXC_NAMES


class CircuitBreaker:
    """Per-provider circuit breaker (process-wide, thread-safe).

    After ``threshold`` consecutive failures a provider's circuit *opens* for
    ``cooldown`` seconds; while open the router skips that provider's rungs and
    goes straight to the next one, so a sustained outage doesn't make every turn
    eat the provider's timeout. A single success resets it.
    """

    def __init__(
        self,
        *,
        threshold: int = CIRCUIT_FAILURE_THRESHOLD,
        cooldown: float = CIRCUIT_COOLDOWN_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._threshold = threshold
        self._cooldown = cooldown
        self._now = monotonic
        self._lock = threading.Lock()
        self._failures: dict[Provider, int] = {}
        self._open_until: dict[Provider, float] = {}

    def is_open(self, provider: Provider) -> bool:
        with self._lock:
            return self._now() < self._open_until.get(provider, 0.0)

    def record_success(self, provider: Provider) -> None:
        with self._lock:
            self._failures[provider] = 0
            self._open_until.pop(provider, None)

    def record_failure(self, provider: Provider) -> None:
        with self._lock:
            count = self._failures.get(provider, 0) + 1
            self._failures[provider] = count
            if count >= self._threshold:
                self._open_until[provider] = self._now() + self._cooldown

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()
            self._open_until.clear()


_default_breaker = CircuitBreaker()


def reset_default_breaker() -> None:
    """Clear the process-wide breaker (used between tests for isolation)."""
    _default_breaker.reset()


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
    """Every configured provider in the chain failed — the final, explicit fallback.

    This is the *outage* type: the providers were unreachable/erroring for
    infrastructure reasons (timeout, 5xx, auth, bad deployment). Callers MUST be
    able to tell this apart from a provider that *declined the request as unsafe*
    (see :class:`ContentFiltered`).
    """


class ContentFiltered(LLMError):
    """A provider's *trained safety classifier* rejected the request as unsafe.

    Distinct from :class:`AllProvidersDown` on purpose: Azure's Responsible-AI
    content filter returns a structured 400 (``code == 'content_filter'`` /
    ``innererror.code == 'ResponsibleAIPolicyViolation'`` /
    ``content_filter_result.jailbreak.detected``) that means "this is an attack",
    not "the service is down". The router surfaces this typed signal so a caller
    (the injection gate) can BLOCK on the provider's authoritative verdict rather
    than failing open as it would on a generic outage.

    Raised only when *every* tier failed AND at least one tier declined for content
    reasons — so the router still tries remaining rungs for availability (a benign
    learner prompt that trips RAI on one tier can still be answered by a fallback),
    but a chain that ends in a safety refusal is reported as one.
    """

    def __init__(self, message: str, *, categories: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        # The RAI categories that fired (e.g. "jailbreak", "violence"), if the
        # structured error exposed them — carried for telemetry, not control flow.
        self.categories = categories


# Structured signatures of a Responsible-AI / content-filter rejection. We read the
# exception's *structured* fields (the openai BadRequestError carries ``.code`` and a
# parsed ``.body`` dict), NOT a substring of ``str(exc)`` — the message text is not a
# stable contract, the structured code is.
_CONTENT_FILTER_CODES = frozenset({"content_filter", "ResponsibleAIPolicyViolation"})


def _content_filter_categories(exc: BaseException) -> tuple[str, ...]:
    """RAI categories that ``detected``/``filtered`` in a structured content-filter error."""
    body = getattr(exc, "body", None)
    if not isinstance(body, dict):
        return ()
    inner = body.get("innererror")
    if not isinstance(inner, dict):
        return ()
    cfr = inner.get("content_filter_result")
    if not isinstance(cfr, dict):
        return ()
    fired: list[str] = []
    for category, result in cfr.items():
        if isinstance(result, dict) and (result.get("detected") or result.get("filtered")):
            fired.append(str(category))
    return tuple(fired)


def _is_content_filter(exc: BaseException) -> bool:
    """True iff ``exc`` is a provider's *structured* content/RAI safety rejection.

    Inspects the structured error shape Azure emits — the top-level ``code``, the
    parsed ``body['code']`` / ``body['innererror']['code']``, or a
    ``content_filter_result.*.detected`` flag — never a substring of the message.
    """
    if getattr(exc, "code", None) in _CONTENT_FILTER_CODES:
        return True
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        if body.get("code") in _CONTENT_FILTER_CODES:
            return True
        inner = body.get("innererror")
        if isinstance(inner, dict):
            if inner.get("code") in _CONTENT_FILTER_CODES:
                return True
            cfr = inner.get("content_filter_result")
            if isinstance(cfr, dict):
                for result in cfr.values():
                    if isinstance(result, dict) and result.get("detected"):
                        return True
    return False


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


@dataclass(frozen=True)
class ToolCall:
    """One tool invocation the model asked for (arguments are a raw JSON string)."""

    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ToolLoopResult:
    """The final assistant text after a tool-calling loop, tagged with its tier."""

    text: str
    provider: Provider
    model: str
    tier: int
    rounds: int


# A tool handler takes the model's parsed arguments and returns a JSON-serializable
# result (dict or str) the model sees as the tool's output.
ToolHandler = Callable[[dict[str, Any]], Any]


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

    def complete_tools(
        self,
        model: str,
        messages: Sequence[dict[str, Any]],
        *,
        tools: list[dict[str, Any]],
        tool_choice: str,
        max_tokens: int,
    ) -> tuple[str, list[ToolCall]]: ...


# ── Real providers (lazy SDK import; only constructed when configured) ─────────


class _OpenAICompatibleProvider:
    """Shared impl for Azure OpenAI and Groq (both speak the OpenAI chat API)."""

    name: Provider

    def __init__(self, client: Any, *, is_azure: bool, timeout: float = 30.0) -> None:
        self._client = client
        self._is_azure = is_azure
        self._timeout = timeout

    def _kwargs(self, model: str, max_tokens: int) -> dict[str, Any]:
        # A per-request timeout so a hung provider degrades to the next rung
        # instead of stalling the whole turn.
        base: dict[str, Any] = {"timeout": self._timeout}
        # o-series (Azure) reject temperature/top_p and rename the token budget.
        if self._is_azure and _is_reasoning_model(model):
            return {**base, "max_completion_tokens": max_tokens}
        # Temperature 0: routing, gating, grounding, and planning are decisions, not
        # creative writing — the same message must classify and answer the same way every
        # time (pass^k determinism). A stochastic gate is exactly what made the system-
        # prompt leak flaky; deterministic decoding removes that whole class of flakiness.
        return {**base, "max_tokens": max_tokens, "temperature": 0.0}

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

    def complete_tools(
        self,
        model: str,
        messages: Sequence[dict[str, Any]],
        *,
        tools: list[dict[str, Any]],
        tool_choice: str,
        max_tokens: int,
    ) -> tuple[str, list[ToolCall]]:
        kwargs = self._kwargs(model, max_tokens)
        response = self._client.chat.completions.create(
            model=model,
            messages=self._project_messages(model, messages),
            tools=tools,
            tool_choice=tool_choice,
            **kwargs,
        )
        message = response.choices[0].message
        calls = [
            ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments or "{}")
            for tc in (getattr(message, "tool_calls", None) or [])
        ]
        return (message.content or ""), calls


def _build_azure_provider(settings: Settings) -> _OpenAICompatibleProvider:
    from app.foundry import build_openai_client

    provider = _OpenAICompatibleProvider(
        build_openai_client(settings.require_foundry()),
        is_azure=True,
        timeout=settings.llm_timeout_seconds,
    )
    provider.name = Provider.AZURE
    return provider


def _build_groq_provider(settings: Settings) -> _OpenAICompatibleProvider:
    from openai import OpenAI

    config = settings.require_groq()
    client = OpenAI(api_key=config.api_key, base_url=config.base_url)
    provider = _OpenAICompatibleProvider(
        client, is_azure=False, timeout=settings.llm_timeout_seconds
    )
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
        breaker: CircuitBreaker | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = RETRY_MAX_ATTEMPTS,
    ) -> None:
        self._settings = settings or get_settings()
        # Providers are lazily built on first use unless injected (tests inject fakes).
        self._azure = azure
        self._groq = groq
        self._azure_built = azure is not None
        self._groq_built = groq is not None
        # Process-wide breaker by default so an outage learned on one turn is
        # honored on the next; injectable + a small sleep hook for fast tests.
        self._breaker = breaker or _default_breaker
        self._sleep = sleep
        self._max_attempts = max(1, max_attempts)

    def _retry(self, call: Callable[[], Any]) -> Any:
        """Run ``call``, retrying only *transient* errors with exponential backoff.

        A non-transient error raises on the first attempt so the caller falls
        straight to the next rung (M6).
        """
        for i in range(self._max_attempts):
            try:
                return call()
            except Exception as exc:  # noqa: BLE001 — classified, then retried or re-raised
                if _is_transient(exc) and i + 1 < self._max_attempts:
                    self._sleep(RETRY_BACKOFF_BASE_SECONDS * (2**i))
                    continue
                raise

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
        attempted = False
        # Track a trained-safety rejection so a chain that ends in a content_filter
        # is reported as ContentFiltered (distinguishable from a real outage), while
        # still trying remaining rungs for availability.
        filter_exc: BaseException | None = None
        for provider, attempt in rungs:
            if self._breaker.is_open(attempt.provider):
                continue  # provider circuit open → skip straight to the next rung
            attempted = True
            started = time.monotonic()
            try:
                raw = self._retry(
                    partial(
                        provider.complete,
                        attempt.model,
                        messages,
                        json_mode=json_mode,
                        max_tokens=max_tokens,
                    )
                )
            except Exception as exc:  # noqa: BLE001 — record and try the next rung
                logger.warning(
                    "tier %d %s/%s failed: %s", attempt.tier, attempt.provider, attempt.model, exc
                )
                last = exc
                if _is_content_filter(exc):
                    filter_exc = exc
                self._breaker.record_failure(attempt.provider)
                continue
            self._breaker.record_success(attempt.provider)
            return LLMResult(
                text=raw.text,
                provider=attempt.provider,
                model=attempt.model,
                tier=attempt.tier,
                prompt_tokens=raw.prompt_tokens,
                completion_tokens=raw.completion_tokens,
                latency_ms=int((time.monotonic() - started) * 1000),
            )
        if not attempted:
            raise AllProvidersDown("all provider circuits are open")
        # Every tier failed. If a provider's trained safety classifier declined the
        # request, that is an authoritative "this is unsafe" signal — surface it as a
        # typed ContentFiltered so the caller can BLOCK, not fail open as on an outage.
        if filter_exc is not None:
            raise ContentFiltered(
                "provider declined the request as unsafe (content filter)",
                categories=_content_filter_categories(filter_exc),
            ) from filter_exc
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
        attempted = False
        for provider, attempt in rungs:
            if self._breaker.is_open(attempt.provider):
                continue  # provider circuit open → skip straight to the next rung
            attempted = True
            try:
                first, iterator = self._retry(
                    partial(_open_stream, provider, attempt.model, messages, max_tokens)
                )
            except StopIteration:
                # Empty stream — treat as a failure and try the next rung.
                last = LLMError(f"tier {attempt.tier} produced no tokens")
                self._breaker.record_failure(attempt.provider)
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
                self._breaker.record_failure(attempt.provider)
                continue
            self._breaker.record_success(attempt.provider)
            return StreamHandle(
                tokens=_prepend(first, iterator),
                provider=attempt.provider,
                model=attempt.model,
                tier=attempt.tier,
            )
        if not attempted:
            raise AllProvidersDown("all provider circuits are open")
        raise AllProvidersDown(f"all {len(rungs)} provider tiers failed") from last

    def run_tools(
        self,
        capability: Capability,
        messages: Sequence[dict[str, Any]],
        *,
        tools: list[dict[str, Any]],
        handlers: dict[str, ToolHandler],
        max_rounds: int = 6,
        max_tokens: int = 1024,
    ) -> ToolLoopResult:
        """Run an LLM tool-calling loop: the model calls tools, we execute the
        handlers and feed results back, until it returns a plain answer.

        The whole loop runs on one provider (you cannot switch providers
        mid-conversation); the fallback chain only chooses *which* provider starts
        it, honoring the circuit breaker. Handlers receive the model's parsed
        arguments and return a JSON-serializable result.
        """
        rungs = [r for r in self.chain(capability) if not self._breaker.is_open(r[1].provider)]
        if not rungs:
            raise AllProvidersDown("no LLM provider available for tools")
        last: Exception | None = None
        for provider, attempt in rungs:
            try:
                result = self._tool_loop(
                    provider, attempt, messages, tools, handlers, max_rounds, max_tokens
                )
            except Exception as exc:  # noqa: BLE001 — record and try the next provider
                logger.warning(
                    "tier %d %s tool loop failed: %s", attempt.tier, attempt.provider, exc
                )
                last = exc
                self._breaker.record_failure(attempt.provider)
                continue
            self._breaker.record_success(attempt.provider)
            return result
        raise AllProvidersDown("all provider tiers failed for tools") from last

    def _tool_loop(
        self,
        provider: CompletionProvider,
        attempt: Attempt,
        messages: Sequence[dict[str, Any]],
        tools: list[dict[str, Any]],
        handlers: dict[str, ToolHandler],
        max_rounds: int,
        max_tokens: int,
    ) -> ToolLoopResult:
        convo: list[dict[str, Any]] = list(messages)
        for round_num in range(1, max_rounds + 1):
            text, calls = provider.complete_tools(
                attempt.model, convo, tools=tools, tool_choice="auto", max_tokens=max_tokens
            )
            if not calls:
                return ToolLoopResult(
                    text=text,
                    provider=attempt.provider,
                    model=attempt.model,
                    tier=attempt.tier,
                    rounds=round_num,
                )
            # Echo the model's tool-call message, then append each tool result.
            convo.append(
                {
                    "role": "assistant",
                    "content": text or None,
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {"name": c.name, "arguments": c.arguments},
                        }
                        for c in calls
                    ],
                }
            )
            for call in calls:
                handler = handlers.get(call.name)
                try:
                    args = json.loads(call.arguments or "{}")
                    if not isinstance(args, dict):
                        args = {}
                except json.JSONDecodeError:
                    args = {}
                result = (
                    handler(args) if handler is not None else {"error": f"unknown tool {call.name}"}
                )
                convo.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": result if isinstance(result, str) else json.dumps(result),
                    }
                )
        # Ran out of rounds: force a final answer with no further tool calls.
        text, _ = provider.complete_tools(
            attempt.model, convo, tools=tools, tool_choice="none", max_tokens=max_tokens
        )
        return ToolLoopResult(
            text=text,
            provider=attempt.provider,
            model=attempt.model,
            tier=attempt.tier,
            rounds=max_rounds,
        )


def _open_stream(
    provider: CompletionProvider, model: str, messages: Sequence[Message], max_tokens: int
) -> tuple[str, Iterator[str]]:
    """Open a stream and peek its first token (raises StopIteration if empty).

    Split out so the open + first-token can be retried as one unit on a transient
    error; a rung only "wins" once it has produced a token (M6).
    """
    iterator = provider.stream(model, messages, max_tokens=max_tokens)
    first = next(iterator)
    return first, iterator


def _prepend(first: str, rest: Iterator[str]) -> Iterator[str]:
    """Re-attach the peeked first token to the front of a stream."""
    yield first
    yield from rest
