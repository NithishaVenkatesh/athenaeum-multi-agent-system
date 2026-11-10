"""Chat title + reply generation for the learner workspace.

Two entry points used by the courses API:

- ``generate_title`` turns a learner's first message into a short chat name.
- ``stream_reply`` yields the assistant's reply token-by-token.

Both have a deterministic **offline** path (no Azure) chosen by
``Settings.llm_offline`` — used by CI, E2E, and smoke runs — and a **live** path
that calls the cheapest Foundry deployment through an injectable
``client_factory`` so tests can exercise the streaming/parse logic without
credentials.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator, Sequence
from typing import Any

from app.config import ProviderConfig, Settings, get_settings

logger = logging.getLogger(__name__)
# Room for a reasoning model's brief deliberation plus the <=6-word title.
_TITLE_MAX_TOKENS = 200

MAX_TITLE_WORDS = 6
MAX_TITLE_CHARS = 48

_TITLE_SYSTEM = (
    "You name chat threads. Reply with a short, specific title of at most six words "
    "for a conversation that begins with the user's message. No surrounding quotes and "
    "no trailing punctuation."
)
_CHAT_SYSTEM = (
    "You are Athenaeum, an enterprise learning assistant. Help the learner understand "
    "their course topic clearly and concisely, with plain language and concrete examples."
)

# Factory that turns validated provider config into an OpenAI-style client.
ClientFactory = Callable[[ProviderConfig], Any]


def _default_client_factory(config: ProviderConfig) -> Any:  # pragma: no cover - thin SDK adapter
    from openai import OpenAI

    return OpenAI(api_key=config.api_key, base_url=config.base_url)


def _fallback_title(content: str) -> str:
    """Deterministic title: first few words of the message (offline / failure path)."""
    words = content.strip().split()
    if not words:
        return "New chat"
    title = " ".join(words[:MAX_TITLE_WORDS])
    if len(title) > MAX_TITLE_CHARS:
        title = title[:MAX_TITLE_CHARS].rstrip()
    return title


def _to_chat_messages(messages: Sequence[dict[str, Any]]) -> list[dict[str, str]]:
    """Project stored message rows to the OpenAI ``{role, content}`` shape."""
    return [{"role": str(m["role"]), "content": str(m["content"])} for m in messages]


def generate_title(
    content: str,
    *,
    settings: Settings | None = None,
    client_factory: ClientFactory = _default_client_factory,
) -> str:
    """Short chat name for a new course, derived from the first message."""
    settings = settings or get_settings()
    if settings.llm_offline:
        return _fallback_title(content)

    # Walk the provider chain (Groq, then Gemini): naming a chat must never fail the
    # request, so any provider error falls to the next and finally to the local title.
    for config in _provider_chain(settings):
        try:
            response = client_factory(config).chat.completions.create(
                model=config.model_fast,
                messages=[
                    {"role": "system", "content": _TITLE_SYSTEM},
                    {"role": "user", "content": content},
                ],
                max_tokens=_TITLE_MAX_TOKENS,
                temperature=0.2,
                **_reasoning_kwargs(config.model_fast, settings),
            )
        except Exception as exc:  # noqa: BLE001 — degrade to the next provider
            logger.warning("chat-title provider failed: %s", type(exc).__name__)
            continue
        text = (response.choices[0].message.content or "").strip().strip('"').strip()
        return text or _fallback_title(content)
    return _fallback_title(content)


def _reasoning_kwargs(model: str, settings: Settings) -> dict[str, Any]:
    """Cap gpt-oss deliberation so the short title budget isn't spent on reasoning."""
    if model.startswith("openai/gpt-oss"):
        return {"reasoning_effort": settings.groq_reasoning_effort}
    return {}


def _provider_chain(settings: Settings) -> list[ProviderConfig]:
    """Configured chat providers in fallback order."""
    chain: list[ProviderConfig] = []
    if settings.groq_configured:
        chain.append(settings.require_groq())
    if settings.gemini_configured:
        chain.append(settings.require_gemini())
    return chain


def _fallback_stream(messages: Sequence[dict[str, Any]]) -> Iterator[str]:
    """Deterministic echo reply, streamed word-by-word (offline path)."""
    last_user = next(
        (str(m["content"]) for m in reversed(messages) if m.get("role") == "user"),
        "",
    )
    reply = (
        "(offline mode) Thanks for your message. Live model replies are disabled in this "
        "environment, so here is a deterministic acknowledgement of what you asked: "
        f"{last_user}"
    )
    for word in reply.split(" "):
        yield word + " "


def stream_reply(
    messages: Sequence[dict[str, Any]],
    *,
    settings: Settings | None = None,
    client_factory: ClientFactory = _default_client_factory,
) -> Iterator[str]:
    """Yield the assistant reply for the conversation so far, token-by-token."""
    settings = settings or get_settings()
    if settings.llm_offline:
        yield from _fallback_stream(messages)
        return

    config = settings.require_chat_provider()
    client = client_factory(config)
    stream = client.chat.completions.create(
        model=config.model_workhorse,
        messages=[{"role": "system", "content": _CHAT_SYSTEM}, *_to_chat_messages(messages)],
        stream=True,
        temperature=0.3,
    )
    for chunk in stream:
        choices = getattr(chunk, "choices", None)
        if not choices:
            continue
        token = getattr(choices[0].delta, "content", None)
        if token:
            yield token
