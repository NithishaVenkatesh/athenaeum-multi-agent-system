"""Offline floor for the manager ACCURACY/RELEVANCE battery.

Reuses the live battery's golden questions (``agent_audit.attacks_manager_quality._ALL``)
as one source of truth, but runs them through the OFFLINE manager chat endpoint so CI
verifies — with no Azure/Groq creds — that every legitimate manager question yields a
safe, non-empty, name-free answer that completes without crashing.

The SEMANTIC half (is the answer actually relevant / accurate / well-grounded) is graded
by the live battery: ``python -m agent_audit.run --layer manager_quality --rounds 2``.
This offline test is the deterministic floor, not a replacement.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from agent_audit.attacks_manager import _member_codenames
from agent_audit.attacks_manager_quality import _ALL
from fastapi.testclient import TestClient

MANAGER_ID = "EMP-011"
_CASES = list(_ALL)


def _run(client: TestClient, text: str, history: list[dict[str, str]]) -> tuple[str, bool]:
    body: dict[str, Any] = {"content": text}
    if history:
        body["history"] = history
    resp = client.post(f"/api/manager/{MANAGER_ID}/chat", json=body)
    assert resp.status_code == 200
    events = [
        json.loads(line[len("data: ") :])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    tokens = "".join(str(e["token"]) for e in events if e.get("type") == "token")
    done = any(e.get("type") == "done" for e in events)
    return tokens, done


@pytest.mark.parametrize("case", _CASES, ids=[c.case_id for c in _CASES])
def test_quality_question_answered_safely_offline(client: TestClient, case: Any) -> None:
    """Each legitimate question completes with a non-empty, name-free answer offline."""
    text, done = _run(client, case.text, case.history)

    assert done, f"{case.case_id}: stream never produced a done event"
    assert text.strip(), f"{case.case_id}: a legitimate question got an empty answer"
    leaked = [n for n in _member_codenames() if re.search(rf"\b{re.escape(n)}\b", text, re.I)]
    assert not leaked, f"{case.case_id}: named individual(s) {leaked} in: {text!r}"
