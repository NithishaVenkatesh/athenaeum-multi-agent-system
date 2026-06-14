"""Skill-gap check endpoints: sample, grade, fresher, deadline."""

from __future__ import annotations

from typing import Any

from app.courses.repository import CourseRepository
from app.db import session_scope
from fastapi.testclient import TestClient

MODULE_IDS = ["cb-c01-m01", "cb-c01-m02", "cb-c01-m03", "cb-c01-m04"]


def _seed_choice_banks(assessments_session: Any) -> None:
    """A choices bank with 5 questions for every cb-c01 module (mix of mcq/msq)."""
    from app.assessments.models import AssessmentBank, BankChoiceQuestion

    for mid in MODULE_IDS:
        bank = AssessmentBank(
            course_id="cb-c01", module_id=mid, kind="choices", title=f"{mid} quiz"
        )
        assessments_session.add(bank)
        assessments_session.commit()
        assessments_session.refresh(bank)
        for i in range(1, 6):
            is_msq = i % 5 == 0
            assessments_session.add(
                BankChoiceQuestion(
                    id=f"{mid}-c{i:02d}",
                    bank_id=bank.id,
                    course_id="cb-c01",
                    module_id=mid,
                    prompt=f"{mid} question {i}?",
                    kind="msq" if is_msq else "mcq",
                    choices=["A", "B", "C", "D"],
                    correct_answers=["A", "B"] if is_msq else ["A"],
                )
            )
    assessments_session.commit()


def _linked_course(client: TestClient) -> str:
    course_id = client.post(
        "/api/courses", json={"persona_id": "EMP-001", "content": "Let us begin"}
    ).json()["id"]
    client.post(f"/api/courses/{course_id}/accept", json={"catalog_id": "cb-c01"})
    return course_id


def test_start_returns_up_to_four_questions_per_module(
    client: TestClient, assessments_session: Any
) -> None:
    _seed_choice_banks(assessments_session)
    course_id = _linked_course(client)
    resp = client.post(f"/api/courses/{course_id}/skill/start")
    assert resp.status_code == 200
    body = resp.json()
    assert body["catalog_id"] == "cb-c01"
    assert len(body["modules"]) == len(MODULE_IDS)
    for mod in body["modules"]:
        assert 1 <= len(mod["questions"]) <= 4
        for q in mod["questions"]:
            assert q["kind"] in ("mcq", "msq")
            assert "correct_answers" not in q  # never leaked


def test_grade_stores_scores_and_appends_message(
    client: TestClient, assessments_session: Any
) -> None:
    _seed_choice_banks(assessments_session)
    course_id = _linked_course(client)
    start = client.post(f"/api/courses/{course_id}/skill/start").json()
    # Answer correctly (A) for the first module's mcq questions, blank elsewhere.
    answers = []
    for idx, mod in enumerate(start["modules"]):
        for q in mod["questions"]:
            picked = ["A"] if (idx == 0 and q["kind"] == "mcq") else []
            answers.append(
                {"module_id": mod["module_id"], "question_id": q["id"], "selections": picked}
            )
    resp = client.post(f"/api/courses/{course_id}/skill/grade", json={"answers": answers})
    assert resp.status_code == 200
    result = resp.json()
    assert 0.0 <= result["overall_fraction"] <= 1.0
    first = next(m for m in result["modules"] if m["module_id"] == "cb-c01-m01")
    assert first["correct"] >= 1  # at least the mcq answers landed
    with session_scope() as s:
        course = CourseRepository(s).get(course_id)
        assert course is not None
        assert course.skill_source == "assessment"
        assert course.skill_scores
        assert any((m.get("meta") or {}).get("skill_result") for m in course.messages)


def test_fresher_sets_zero_scores_for_every_module(client: TestClient) -> None:
    course_id = _linked_course(client)
    resp = client.post(f"/api/courses/{course_id}/skill/fresher")
    assert resp.status_code == 200
    assert resp.json()["fresher"] is True
    with session_scope() as s:
        course = CourseRepository(s).get(course_id)
        assert course is not None
        assert course.skill_source == "fresher"
        assert course.skill_scores
        assert set(course.skill_scores) == set(MODULE_IDS)
        assert all(v == 0.0 for v in course.skill_scores.values())


def test_deadline_sets_and_clears(client: TestClient) -> None:
    course_id = _linked_course(client)
    client.post(f"/api/courses/{course_id}/skill/fresher")
    assert (
        client.post(
            f"/api/courses/{course_id}/deadline", json={"deadline": "2026-08-01"}
        ).status_code
        == 204
    )
    with session_scope() as s:
        assert CourseRepository(s).get(course_id).plan_exam_date == "2026-08-01"  # type: ignore[union-attr]
    client.post(f"/api/courses/{course_id}/deadline", json={"deadline": None})
    with session_scope() as s:
        assert CourseRepository(s).get(course_id).plan_exam_date is None  # type: ignore[union-attr]


def test_start_requires_linked_course(client: TestClient) -> None:
    course_id = client.post("/api/courses", json={"persona_id": "EMP-001", "content": "hi"}).json()[
        "id"
    ]
    assert client.post(f"/api/courses/{course_id}/skill/start").status_code == 409


def _ids(check: dict[str, Any]) -> list[str]:
    """Flat list of sampled question ids across all modules (sample identity)."""
    return [q["id"] for mod in check["modules"] for q in mod["questions"]]


def test_start_persists_active_check_and_get_exposes_it(
    client: TestClient, assessments_session: Any
) -> None:
    """The sampled quiz is stored on the course so the card survives a chat switch."""
    _seed_choice_banks(assessments_session)
    course_id = _linked_course(client)
    started = client.post(f"/api/courses/{course_id}/skill/start").json()

    with session_scope() as s:
        course = CourseRepository(s).get(course_id)
        assert course is not None
        assert course.skill_check_active  # non-empty payload persisted
        assert _ids(course.skill_check_active) == _ids(started)

    # GET /courses/{id} exposes it so the frontend can restore the open quiz.
    reloaded = client.get(f"/api/courses/{course_id}").json()
    assert reloaded["skill_check_active"] is not None
    assert _ids(reloaded["skill_check_active"]) == _ids(started)


def test_start_returns_same_questions_until_resolved(
    client: TestClient, assessments_session: Any
) -> None:
    """Re-starting an unresolved check returns the same sample (stable across reload)."""
    _seed_choice_banks(assessments_session)
    course_id = _linked_course(client)
    first = client.post(f"/api/courses/{course_id}/skill/start").json()
    second = client.post(f"/api/courses/{course_id}/skill/start").json()
    assert _ids(first) == _ids(second)


def test_grade_clears_active_check(client: TestClient, assessments_session: Any) -> None:
    """Grading resolves the skill step, so the open-quiz payload is cleared."""
    _seed_choice_banks(assessments_session)
    course_id = _linked_course(client)
    start = client.post(f"/api/courses/{course_id}/skill/start").json()
    answers = [
        {"module_id": mod["module_id"], "question_id": q["id"], "selections": []}
        for mod in start["modules"]
        for q in mod["questions"]
    ]
    client.post(f"/api/courses/{course_id}/skill/grade", json={"answers": answers})
    with session_scope() as s:
        course = CourseRepository(s).get(course_id)
        assert course is not None
        assert not course.skill_check_active
    assert client.get(f"/api/courses/{course_id}").json()["skill_check_active"] is None


def test_fresher_clears_active_check(client: TestClient, assessments_session: Any) -> None:
    """Choosing fresher resolves the skill step and clears any open-quiz payload."""
    _seed_choice_banks(assessments_session)
    course_id = _linked_course(client)
    client.post(f"/api/courses/{course_id}/skill/start")
    client.post(f"/api/courses/{course_id}/skill/fresher")
    with session_scope() as s:
        course = CourseRepository(s).get(course_id)
        assert course is not None
        assert not course.skill_check_active
    assert client.get(f"/api/courses/{course_id}").json()["skill_check_active"] is None
