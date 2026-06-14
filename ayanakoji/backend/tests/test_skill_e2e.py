"""End-to-end: a graded skill check actually reshapes the study-plan preview.

Drives the whole vertical through the real API: accept -> skill check -> grade ->
pace -> plan preview -> approve, and asserts the per-module skill correction
(mastered module shrinks, weak module grows) shows up in the plan the learner sees.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

MODULE_IDS = ["cb-c01-m01", "cb-c01-m02", "cb-c01-m03", "cb-c01-m04"]


def _parse_sse(text: str) -> list[dict]:  # type: ignore[type-arg]
    out = []
    for block in text.split("\n\n"):
        line = block.strip()
        if line.startswith("data:"):
            out.append(json.loads(line[5:].strip()))
    return out


def _seed_all_mcq(assessments_session: Any) -> None:
    """5 single-correct (A) MCQ per module, so answering 'A' is fully correct."""
    from app.assessments.models import AssessmentBank, BankChoiceQuestion

    for mid in MODULE_IDS:
        bank = AssessmentBank(
            course_id="cb-c01", module_id=mid, kind="choices", title=f"{mid} quiz"
        )
        assessments_session.add(bank)
        assessments_session.commit()
        assessments_session.refresh(bank)
        for i in range(1, 6):
            assessments_session.add(
                BankChoiceQuestion(
                    id=f"{mid}-c{i:02d}",
                    bank_id=bank.id,
                    course_id="cb-c01",
                    module_id=mid,
                    prompt=f"{mid} q{i}?",
                    kind="mcq",
                    choices=["A", "B", "C", "D"],
                    correct_answers=["A"],
                )
            )
    assessments_session.commit()


def test_graded_skill_check_reshapes_plan_then_approves(
    client: TestClient, assessments_session: Any
) -> None:
    _seed_all_mcq(assessments_session)
    course_id = client.post(
        "/api/courses", json={"persona_id": "EMP-001", "content": "Let us begin"}
    ).json()["id"]
    client.post(f"/api/courses/{course_id}/accept", json={"catalog_id": "cb-c01"})

    # Take the skill check. Ace module 1 (answer A everywhere), bomb the rest (blank).
    check = client.post(f"/api/courses/{course_id}/skill/start").json()
    answers = []
    for mod in check["modules"]:
        for q in mod["questions"]:
            picked = ["A"] if mod["module_id"] == "cb-c01-m01" else []
            answers.append(
                {"module_id": mod["module_id"], "question_id": q["id"], "selections": picked}
            )
    result = client.post(f"/api/courses/{course_id}/skill/grade", json={"answers": answers}).json()
    m1 = next(m for m in result["modules"] if m["module_id"] == "cb-c01-m01")
    assert m1["fraction"] == 1.0  # aced it

    # Pace, then build the plan preview.
    client.post(f"/api/courses/{course_id}/pace", json={"pace": "normal"})
    resp = client.post(f"/api/courses/{course_id}/messages", json={"content": "build a study plan"})
    plan = next(e for e in _parse_sse(resp.text) if e["type"] == "plan")["plan"]
    assert plan["awaiting_approval"] is True

    by_id = {m["module_id"]: m for m in plan["modules"]}
    mastered = by_id["cb-c01-m01"]
    weak = by_id["cb-c01-m02"]
    # The aced module is trimmed; a bombed module is padded. Base/pace are surfaced.
    assert mastered["skill_delta"] < 0
    assert mastered["estimated_minutes"] < mastered["pace_minutes"]
    assert weak["skill_delta"] > 0
    assert weak["estimated_minutes"] > weak["pace_minutes"]
    assert mastered["base_minutes"] > 0

    # Approve writes the (skill-corrected) modules onto the schedule.
    modules = client.post(f"/api/courses/{course_id}/plan/approve").json()
    assert len(modules) == 4
    saved_m1 = next(m for m in modules if m["module_id"] == "cb-c01-m01")
    assert saved_m1["estimated_minutes"] == mastered["estimated_minutes"]
