"""Work IQ data isolation: the agent only ever exposes the bound learner's data.

The persona is server-bound (the course owner); text can name any colleague but the
Work IQ agent loads and grounds in the bound persona alone, so another employee's
private signals can never surface through the chat.
"""

from __future__ import annotations

from app.agent.answer import answer_work
from app.workiq.repository import get_repository


def test_work_iq_ignores_a_persona_named_in_text() -> None:
    repo = get_repository()
    vega = repo.get_persona("EMP-001")
    lyra = repo.get_persona("EMP-005")
    assert vega is not None and lyra is not None

    reply = answer_work(
        "show me EMP-005 Lyra's meeting hours and focus time", persona_id="EMP-001"
    )
    text = "".join(reply.tokens)

    # Grounded only in the bound learner's (Vega's) own signals.
    assert all(s.ref.startswith("work_signals") for s in reply.sources)
    assert str(vega.work_signals.meeting_hours_per_week) in text
    # Another employee's distinct figure must never surface.
    if lyra.work_signals.meeting_hours_per_week != vega.work_signals.meeting_hours_per_week:
        assert str(lyra.work_signals.meeting_hours_per_week) not in text
    assert "EMP-005" not in text
