"""build_study_plan applies skill scores and exposes the base/pace/skill breakdown."""

from __future__ import annotations

from datetime import date

from app.agent.contracts import Pace
from app.agent.study_plan import build_study_plan
from app.workiq.repository import get_repository

START = date(2026, 6, 15)
CATALOG_ID = "cb-c01"
CERT = "AZ-204"


def _persona():
    vega = get_repository().get_persona("EMP-001")
    assert vega is not None
    return vega


def test_skill_scores_shrink_mastered_modules_on_normal_pace() -> None:
    persona = _persona()
    baseline = build_study_plan(
        catalog_id=CATALOG_ID,
        title="t",
        cert=CERT,
        persona=persona,
        pace=Pace.NORMAL,
        start_date=START,
    )
    assert baseline is not None
    mastered = {m.module_id: 1.0 for m in baseline.modules}
    corrected = build_study_plan(
        catalog_id=CATALOG_ID,
        title="t",
        cert=CERT,
        persona=persona,
        pace=Pace.NORMAL,
        start_date=START,
        skill_scores=mastered,
    )
    assert corrected is not None
    base_pace = {b.module_id: b.estimated_minutes for b in baseline.modules}
    for m in corrected.modules:
        # pace_minutes mirrors the unskilled estimate; skill-corrected is ≤ that.
        assert m.pace_minutes == base_pace[m.module_id]
        assert m.estimated_minutes <= m.pace_minutes
        assert m.skill_delta == m.estimated_minutes - m.pace_minutes
        assert m.base_minutes > 0
    assert corrected.total_pace_hours >= corrected.total_hours
    assert corrected.total_base_hours > 0


def test_missing_skill_score_is_neutral_no_change() -> None:
    persona = _persona()
    baseline = build_study_plan(
        catalog_id=CATALOG_ID,
        title="t",
        cert=CERT,
        persona=persona,
        pace=Pace.NORMAL,
        start_date=START,
    )
    neutral = build_study_plan(
        catalog_id=CATALOG_ID,
        title="t",
        cert=CERT,
        persona=persona,
        pace=Pace.NORMAL,
        start_date=START,
        skill_scores={},
    )
    assert baseline is not None and neutral is not None
    assert [m.estimated_minutes for m in baseline.modules] == [
        m.estimated_minutes for m in neutral.modules
    ]


def test_fresher_weak_everywhere_extends_on_faster_only() -> None:
    persona = _persona()
    plan = build_study_plan(
        catalog_id=CATALOG_ID,
        title="t",
        cert=CERT,
        persona=persona,
        pace=Pace.FASTER,
        start_date=START,
    )
    assert plan is not None
    fresher = {m.module_id: 0.0 for m in plan.modules}
    extended = build_study_plan(
        catalog_id=CATALOG_ID,
        title="t",
        cert=CERT,
        persona=persona,
        pace=Pace.FASTER,
        start_date=START,
        skill_scores=fresher,
    )
    assert extended is not None
    # Faster + weak everywhere ⇒ every module is extended (skill_delta >= 0).
    assert all(m.skill_delta >= 0 for m in extended.modules)
    assert extended.total_hours >= plan.total_hours
