"""Microsoft Foundry / Azure OpenAI connectivity layer.

SDK imports are lazy (inside functions) so this module imports cleanly in the
offline CI lane where the ``foundry`` dependency group is not installed. The
real work lives behind functions that require those packages + live credentials.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.config import FoundryConfig, Settings, get_settings

if TYPE_CHECKING:
    from openai import AzureOpenAI


@dataclass(frozen=True)
class SmokeResult:
    """Outcome of a Foundry connectivity smoke test."""

    ok: bool
    detail: str
    model: str
    reply: str | None = None


def build_openai_client(config: FoundryConfig) -> AzureOpenAI:
    """Construct an Azure OpenAI client from validated Foundry config (API-key auth)."""
    from openai import AzureOpenAI

    return AzureOpenAI(
        azure_endpoint=config.openai_endpoint,
        api_key=config.openai_api_key,
        api_version=config.openai_api_version,
    )


def smoke_check(settings: Settings | None = None) -> SmokeResult:
    """Minimal, cheap (≤5 token) round-trip to the workhorse deployment.

    Returns a structured result instead of raising, so callers (CLI smoke,
    health surfaces) can report cleanly. Fails loud only on misconfiguration.
    """
    settings = settings or get_settings()
    config = settings.require_foundry()  # raises with a clear message if unset

    try:
        client = build_openai_client(config)
        response = client.chat.completions.create(
            model=config.model_workhorse,
            messages=[
                {"role": "system", "content": "You are a connectivity probe."},
                {"role": "user", "content": "Reply with the single word: pong"},
            ],
            max_tokens=5,
            temperature=0,
        )
        reply = (response.choices[0].message.content or "").strip()
        return SmokeResult(
            ok=True,
            detail="Azure OpenAI chat completion succeeded",
            model=config.model_workhorse,
            reply=reply,
        )
    except Exception as exc:  # noqa: BLE001 — surface any SDK/network error as a result
        return SmokeResult(
            ok=False,
            detail=f"{type(exc).__name__}: {exc}",
            model=config.model_workhorse,
        )


def project_check(settings: Settings | None = None) -> SmokeResult:
    """Best-effort Foundry project connectivity via AIProjectClient (DefaultAzureCredential).

    Requires an Azure login / managed identity with access to the project. Reported
    separately from the API-key OpenAI path so one can pass while the other is pending RBAC.
    """
    settings = settings or get_settings()
    config = settings.require_foundry()

    try:
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential

        client = AIProjectClient(
            endpoint=config.project_endpoint,
            credential=DefaultAzureCredential(),
        )
        # Listing deployments is a light read that proves auth + project reachability.
        names = [getattr(d, "name", "?") for d in client.deployments.list()]
        return SmokeResult(
            ok=True,
            detail=f"Foundry project reachable; {len(names)} deployment(s): {', '.join(names)}",
            model=config.model_workhorse,
        )
    except Exception as exc:  # noqa: BLE001
        return SmokeResult(
            ok=False,
            detail=f"{type(exc).__name__}: {exc}",
            model=config.model_workhorse,
        )
