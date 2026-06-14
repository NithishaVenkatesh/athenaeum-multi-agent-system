"""Fabrication-guard tests: citation guard (A2) + role/word number guard (A3/A4)."""

from __future__ import annotations

from datetime import date

import pytest
from app.agent.contracts import GroundingSource
from app.agent.guards import (
    cited_refs,
    plan_narration_is_grounded,
    stream_grounded,
    strip_unknown_citations,
)
from app.agent.study_plan import build_study_plan
from app.workiq.repository import get_repository


def _sources() -> list[GroundingSource]:
    return [GroundingSource(ref="cb-c01-m02", title="t", snippet="s")]


# ── A2: citation guard is no longer bracket-bound ───────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "as covered in [cb-c99-m99]",  # bracketed phantom
        "as covered in (cb-c99-m99)",  # parenthesized phantom
        "as covered in cb-c99-m99 directly",  # bare phantom in prose
    ],
)
def test_strip_removes_phantom_in_any_format(text: str) -> None:
    out = strip_unknown_citations(text, _sources())
    assert "cb-c99-m99" not in out, f"phantom survived: {out!r}"


def test_strip_keeps_real_citation_any_format() -> None:
    assert "cb-c01-m02" in strip_unknown_citations("see cb-c01-m02 and [cb-c01-m02]", _sources())


def test_cited_refs_sees_bare_ids() -> None:
    assert "cb-c99-m99" in cited_refs("attributed to cb-c99-m99 in the text")


def test_stream_drops_bare_phantom_id() -> None:
    out = "".join(stream_grounded(["Functions ", "scale, ", "see cb-c99-m99 now"], _sources()))
    assert "cb-c99-m99" not in out
    assert "Functions" in out


# ── A3/A4: number guard is role-aware and reads spelled-out figures ─────────────


def _plan():
    vega = get_repository().get_persona("EMP-001")
    assert vega is not None
    plan = build_study_plan(
        catalog_id="cb-c01", title="x", cert="AZ-204", persona=vega, start_date=date(2026, 6, 15)
    )
    assert plan is not None
    return plan


def test_role_blind_claim_is_caught() -> None:
    """A3: claiming the week-count as the module-count is rejected (digit is 'present')."""
    plan = _plan()
    n, w = len(plan.modules), plan.weeks
    if n == w:
        pytest.skip("module count equals week count for this plan; role mismatch not expressible")
    # 'w modules' — w IS a real plan number (weeks) but the wrong role for 'modules'.
    assert not plan_narration_is_grounded(f"all {w} modules across {w} weeks", plan)
    # The correctly-roled statement is grounded.
    assert plan_narration_is_grounded(f"{n} modules across {w} weeks", plan)


def test_spelled_out_number_is_caught() -> None:
    """A4: a spelled-out ungrounded figure no longer slips past \\d+ matching."""
    plan = _plan()
    if plan.weeks == 20:
        pytest.skip("plan happens to be 20 weeks")
    assert not plan_narration_is_grounded("this runs about twenty weeks in total", plan)
