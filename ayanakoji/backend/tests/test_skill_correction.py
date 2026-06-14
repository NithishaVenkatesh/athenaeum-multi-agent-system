"""Skill-gap time correction: pace-gated, ±20% at the score extremes."""

from __future__ import annotations

import pytest
from app.agent.contracts import Pace
from app.agent.study_plan import apply_skill_correction, skill_factor


@pytest.mark.parametrize(
    ("score", "pace", "expected"),
    [
        # Normal: both directions, ±20% at the extremes, neutral at 0.5.
        (1.0, Pace.NORMAL, 0.80),
        (0.0, Pace.NORMAL, 1.20),
        (0.5, Pace.NORMAL, 1.00),
        (0.75, Pace.NORMAL, 0.90),
        (0.25, Pace.NORMAL, 1.10),
        # Slower: lessen only — mastery shrinks, weakness is clamped to no-change.
        (1.0, Pace.SLOWER, 0.80),
        (0.0, Pace.SLOWER, 1.00),
        (0.5, Pace.SLOWER, 1.00),
        # Faster: extend only — weakness grows, mastery is clamped to no-change.
        (0.0, Pace.FASTER, 1.20),
        (1.0, Pace.FASTER, 1.00),
        (0.5, Pace.FASTER, 1.00),
    ],
)
def test_skill_factor_is_pace_gated(score: float, pace: Pace, expected: float) -> None:
    assert skill_factor(score, pace) == pytest.approx(expected)


def test_fresher_zero_score_extends_only_on_faster_and_normal() -> None:
    # Fresher = score 0.0 everywhere; slower must not pad (lessen-only).
    assert skill_factor(0.0, Pace.SLOWER) == pytest.approx(1.00)
    assert skill_factor(0.0, Pace.NORMAL) == pytest.approx(1.20)
    assert skill_factor(0.0, Pace.FASTER) == pytest.approx(1.20)


def test_apply_skill_correction_rounds_to_granularity_and_respects_direction() -> None:
    # 120 min pace-corrected; mastered (0.8x) → 96 → rounds to 90 (15-min grid).
    assert apply_skill_correction(120, 1.0, Pace.NORMAL) == 90
    # Weak on faster (1.2x) → 144 → rounds to 150.
    assert apply_skill_correction(120, 0.0, Pace.FASTER) == 150
    # Slower never extends: weak score keeps the pace-corrected value.
    assert apply_skill_correction(120, 0.0, Pace.SLOWER) == 120
    # Faster never shrinks: mastered score keeps the pace-corrected value.
    assert apply_skill_correction(120, 1.0, Pace.FASTER) == 120
    # Floor at one granularity unit.
    assert apply_skill_correction(15, 1.0, Pace.NORMAL) >= 15
