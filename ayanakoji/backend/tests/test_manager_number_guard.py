"""Manager chat number guard: the live LLM may only state figures the team aggregates
support; any invented number falls back to the deterministic grounded narration.

Mirrors the learner study-plan number guard (``app.agent.answer``): the model never
originates a statistic. These tests drive the LIVE path with a stub router (the suite is
otherwise forced offline by the autouse ``_offline_env`` fixture).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.agent.llm import StreamHandle
from app.manager.agent import (
    _allowed_numbers,
    _answer,
    _member_count_violations,
    _member_numbers,
    _offline_narration,
    _sources,
)
from app.manager.service import build_team_insights
from app.workiq.repository import get_repository

MANAGER_ID = "EMP-011"


class _FakeRouter:
    """A router whose only job is to hand back one canned reply as a token stream."""

    def __init__(self, reply: str) -> None:
        self._reply = reply

    def stream(self, capability: Any, messages: Any, *, max_tokens: int) -> StreamHandle:
        return StreamHandle(tokens=iter([self._reply]), provider="fake", model="fake-model", tier=1)


def _insights(session: Any):  # noqa: ANN202 — test helper
    repo = get_repository()
    manager = repo.get_persona(MANAGER_ID)
    assert manager is not None
    return build_team_insights(repo, session, manager)


def _live_settings() -> Any:
    """A stand-in that forces the live LLM branch. ``Settings.llm_offline`` is a computed
    property (always True with no provider configured), so it can't be overridden by copy;
    ``_answer`` only reads ``.llm_offline`` when a router is supplied, so this suffices."""
    return SimpleNamespace(llm_offline=False)


def _drain(tokens: Any) -> str:
    return "".join(tokens)


def test_ungrounded_number_falls_back_to_grounded_narration(session: Any) -> None:
    insights = _insights(session)
    assert insights is not None
    # 82 is not a real team figure (and not a derivable percentage), so it is "invented".
    reply = "An impressive 82% of the team is fully ready for certification."
    tel, tokens = _answer(
        "how ready are we?",
        insights,
        "overview",
        _sources(insights),
        history=None,
        router=_FakeRouter(reply),  # type: ignore[arg-type]
        settings=_live_settings(),
    )
    out = _drain(tokens)

    assert "82" not in out  # the invented figure never reaches the client
    guard = next(s for s in tel.steps if s.label == "Number guard")
    assert guard.passed is False
    # Fell back to the deterministic, provably-grounded narration.
    assert out.strip() == _offline_narration(insights, "overview").strip()


def test_grounded_answer_passes_through_unchanged(session: Any) -> None:
    insights = _insights(session)
    assert insights is not None
    # Real, correctly-attributed figures (10 engineers on the team, 0 GO on a fresh DB).
    reply = "The team has 10 engineers, and 0 are ready (GO) so far."
    tel, tokens = _answer(
        "readiness?",
        insights,
        "overview",
        _sources(insights),
        history=None,
        router=_FakeRouter(reply),  # type: ignore[arg-type]
        settings=_live_settings(),
    )
    out = _drain(tokens)

    guard = next(s for s in tel.steps if s.label == "Number guard")
    assert guard.passed is True
    assert "10 engineers" in out


def test_miscounting_people_falls_back(session: Any) -> None:
    """The reported '8 members completed a course' bug: 8 is a real figure (assessment
    attempts) but NOT a member count, so attaching it to 'members' must trigger fallback."""
    insights = _insights(session)
    assert insights is not None
    assert "8" not in _member_numbers(insights)  # 8 is not a real people-count here
    reply = "Great news: 8 members have completed a course in their certification path."
    tel, tokens = _answer(
        "how many have completed a course?",
        insights,
        "overview",
        _sources(insights),
        history=None,
        router=_FakeRouter(reply),  # type: ignore[arg-type]
        settings=_live_settings(),
    )
    out = _drain(tokens)

    guard = next(s for s in tel.steps if s.label == "Number guard")
    assert guard.passed is False
    assert "8 members" not in out  # the false people-count never reaches the client
    assert out.strip() == _offline_narration(insights, "overview").strip()


def test_member_count_violations_flags_only_wrong_people_counts(session: Any) -> None:
    insights = _insights(session)
    assert insights is not None
    total = insights.member_count  # real people-count
    # A real member-count attached to a people-noun is fine; a non-member figure is not.
    assert _member_count_violations(f"{total} engineers are on the team", insights) == set()
    assert _member_count_violations("8 members are ready", insights) == {"8"}
    # A non-people figure (assessment attempts) is NOT a member claim → not flagged here.
    assert _member_count_violations("the team passed 8 assessments", insights) == set()
    # A cert code's digits ("AZ-305 members") must NOT be read as a people-count.
    assert _member_count_violations("the AZ-305 members are progressing", insights) == set()


def test_allowed_numbers_include_real_aggregates_not_invented(session: Any) -> None:
    insights = _insights(session)
    assert insights is not None
    allowed = _allowed_numbers(insights)
    # The team size and GO count are legitimate; a made-up 82 is not.
    assert str(insights.member_count) in allowed
    assert str(insights.readiness.go) in allowed
    assert "82" not in allowed
