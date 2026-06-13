"""Live Foundry integration smoke (skipped without the SDK group or credentials).

In the offline CI lane the ``openai`` package is absent, so importorskip skips the
whole module. Locally with `.env` + the foundry group it performs a ~0-cost call.
"""

from __future__ import annotations

import pytest

pytest.importorskip("openai", reason="foundry dependency group not installed")

from app.config import get_settings  # noqa: E402
from app.foundry import smoke_check  # noqa: E402

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _require_credentials() -> None:
    if not get_settings().foundry_configured:
        pytest.skip("Foundry credentials not configured (.env missing)")


def test_azure_openai_chat_completion_roundtrip() -> None:
    result = smoke_check()

    assert result.ok, f"smoke failed: {result.detail}"
    assert result.model == "gpt-4o-mini"
    assert result.reply is not None
    assert "pong" in result.reply.lower()
