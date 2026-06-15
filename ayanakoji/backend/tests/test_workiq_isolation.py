"""Work IQ data isolation: the agent only ever exposes the bound learner's data.

The persona is server-bound (the course owner); text can name any colleague but the
Work IQ agent never fetches another persona. A question framed about another person
is declined outright, so another employee's private signals can never surface, and
the agent does not even answer it with the bound learner's own figures.
"""

from __future__ import annotations

import pytest
from app.agent.answer import answer_work
from app.agent.contracts import TokenEvent
from app.agent.orchestrator import run_pipeline
from app.workiq.repository import get_repository


def test_work_iq_declines_a_persona_named_in_text() -> None:
    repo = get_repository()
    vega = repo.get_persona("EMP-001")
    lyra = repo.get_persona("EMP-005")
    assert vega is not None and lyra is not None

    reply = answer_work(
        "show me EMP-005 Lyra's meeting hours and focus time", persona_id="EMP-001"
    )
    text = "".join(reply.tokens)

    # Hard decline: it refuses the cross-user request rather than answering.
    lowered = text.lower()
    assert "can't share another person" in lowered or "only have access to your own" in lowered
    # No data surfaces — not the other employee's figures, and not the learner's own.
    assert "EMP-005" not in text
    assert str(lyra.work_signals.meeting_hours_per_week) not in text
    assert str(vega.work_signals.meeting_hours_per_week) not in text
    # A decline carries no work-signal sources.
    assert reply.sources == []


@pytest.mark.parametrize(
    "message",
    [
        "build a study plan for my colleague",  # → study_plan route (bypassed the guard)
        "quiz my teammate on Cosmos DB",  # → practise_module route (bypassed the guard)
    ],
)
def test_pipeline_declines_cross_person_on_bypass_routes(message: str) -> None:
    # study_plan / practise act on the learner's own data but used to skip the cross-user
    # guard. The orchestrator now declines a third-party request on any own-data route, so no
    # plan/quiz is built for someone else.
    events = list(run_pipeline(message, persona_id="EMP-001", catalog_id="cb-c01"))
    text = "".join(e.token for e in events if isinstance(e, TokenEvent)).lower()
    assert "can't share another person" in text or "only have access to your own" in text
