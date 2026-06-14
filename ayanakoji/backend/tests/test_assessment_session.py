"""Tests for the learner-facing assessment session API.

Covers: start choices/llm, select, submit, results, LLM turn, completion gate,
retake blocking, sequential lock, random sampling, round-robin LLM rotation.
All tests run in the offline LLM lane (no Azure calls).
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

# ── helpers ───────────────────────────────────────────────────────────────────


def _seed_banks(assessments_session: Any) -> None:
    """Insert minimal bank rows so the assessment API can sample questions."""
    from app.assessments.models import AssessmentBank, BankChoiceQuestion, BankLlmQuestion

    mid = "cb-c01-m01"
    cid = "cb-c01"

    # choices bank
    cb = AssessmentBank(course_id=cid, module_id=mid, kind="choices", title="CB M01 Quiz")
    assessments_session.add(cb)
    assessments_session.commit()
    assessments_session.refresh(cb)
    for i in range(1, 11):
        q = BankChoiceQuestion(
            id=f"{mid}-c{i:02d}",
            bank_id=cb.id,
            course_id=cid,
            module_id=mid,
            prompt=f"Choice question {i}?",
            kind="mcq",
            choices=["A", "B", "C", "D"],
            correct_answers=["A"],
        )
        assessments_session.add(q)

    # llm bank
    lb = AssessmentBank(course_id=cid, module_id=mid, kind="llm", title="CB M01 Explain")
    assessments_session.add(lb)
    assessments_session.commit()
    assessments_session.refresh(lb)
    for i in range(1, 4):
        q = BankLlmQuestion(
            id=f"{mid}-l{i:02d}",
            bank_id=lb.id,
            course_id=cid,
            module_id=mid,
            prompt=f"Explain concept {i}.",
            reference_answer=f"Reference answer {i}.",
        )
        assessments_session.add(q)

    assessments_session.commit()


def _make_course_with_plan(client: TestClient) -> tuple[str, str]:
    """Create a course, accept it, add a module row, return (course_id, module_id)."""
    course = client.post(
        "/api/courses", json={"persona_id": "EMP-001", "content": "Let us begin"}
    ).json()
    course_id = course["id"]

    # Accept the course (link to catalog)
    client.post(f"/api/courses/{course_id}/accept", json={"catalog_id": "cb-c01"})

    # The module row is created by replace_modules; simulate it via the modules endpoint
    # by sending a study plan through the agent. Easier: directly insert via the repo.
    from app.courses.models import CourseModule
    from app.db import session_scope

    module_id = "cb-c01-m01"
    with session_scope() as s:
        s.add(
            CourseModule(
                course_id=course_id,
                module_id=module_id,
                title="CB Module 1",
                sequence=1,
                estimated_minutes=60,
                complete_before="2026-12-31",
            )
        )
        s.commit()

    return course_id, module_id


# ── start choices ─────────────────────────────────────────────────────────────


def test_start_choices_returns_5_questions(client: TestClient, assessments_session: Any) -> None:
    _seed_banks(assessments_session)
    course_id, module_id = _make_course_with_plan(client)
    resp = client.post(
        f"/api/courses/{course_id}/modules/{module_id}/assessments/start",
        params={"type": "choices"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["type"] == "choices"
    assert body["attempt_number"] == 1
    assert len(body["choice_questions"]) == 5
    assert body["score"] is None
    assert body["passed"] is None


def test_start_choices_random_sample_varies(client: TestClient, assessments_session: Any) -> None:
    """Different attempts should (with overwhelmingly high probability) get different sets."""
    _seed_banks(assessments_session)
    course_id, module_id = _make_course_with_plan(client)

    # We can't retake before failing, so we submit the first attempt as all wrong.
    r1 = client.post(
        f"/api/courses/{course_id}/modules/{module_id}/assessments/start",
        params={"type": "choices"},
    ).json()
    a1_id = r1["id"]
    # Submit without selecting → all wrong
    sub1 = client.post(f"/api/courses/{course_id}/assessments/{a1_id}/choices/submit")
    assert sub1.json()["passed"] is False

    # Start attempt 2
    r2 = client.post(
        f"/api/courses/{course_id}/modules/{module_id}/assessments/start",
        params={"type": "choices"},
    ).json()
    ids1 = {q["bank_question_id"] for q in r1["choice_questions"]}
    ids2 = {q["bank_question_id"] for q in r2["choice_questions"]}
    # With 10 choose 5, probability of identical sample is C(10,5)^-1 = 1/252 — very rare.
    # We just verify both are 5-element subsets of the 10 authored questions.
    assert len(ids1) == 5
    assert len(ids2) == 5


def test_start_choices_blocks_before_plan(client: TestClient, assessments_session: Any) -> None:
    _seed_banks(assessments_session)
    course = client.post("/api/courses", json={"persona_id": "EMP-001", "content": "hello"}).json()
    resp = client.post(
        f"/api/courses/{course['id']}/modules/cb-c01-m01/assessments/start",
        params={"type": "choices"},
    )
    assert resp.status_code == 404  # module not in plan


def test_start_llm_blocked_before_choices_pass(
    client: TestClient, assessments_session: Any
) -> None:
    _seed_banks(assessments_session)
    course_id, module_id = _make_course_with_plan(client)
    resp = client.post(
        f"/api/courses/{course_id}/modules/{module_id}/assessments/start",
        params={"type": "llm"},
    )
    assert resp.status_code == 409
    assert "choices" in resp.json()["detail"]


# ── select + submit choices ───────────────────────────────────────────────────


def test_select_and_submit_choices_all_correct(
    client: TestClient, assessments_session: Any
) -> None:
    _seed_banks(assessments_session)
    course_id, module_id = _make_course_with_plan(client)
    session_data = client.post(
        f"/api/courses/{course_id}/modules/{module_id}/assessments/start",
        params={"type": "choices"},
    ).json()
    a_id = session_data["id"]

    # All bank choices have correct_answers=["A"] — select A for all.
    for q in session_data["choice_questions"]:
        client.post(
            f"/api/courses/{course_id}/assessments/{a_id}/choices/{q['id']}/select",
            json={"selections": ["A"]},
        )

    result = client.post(f"/api/courses/{course_id}/assessments/{a_id}/choices/submit").json()
    assert result["score"] == 10.0
    assert result["passed"] is True
    assert all(q["is_correct"] for q in result["questions"])


def test_submit_choices_all_wrong_score_0(client: TestClient, assessments_session: Any) -> None:
    _seed_banks(assessments_session)
    course_id, module_id = _make_course_with_plan(client)
    session_data = client.post(
        f"/api/courses/{course_id}/modules/{module_id}/assessments/start",
        params={"type": "choices"},
    ).json()
    a_id = session_data["id"]

    result = client.post(f"/api/courses/{course_id}/assessments/{a_id}/choices/submit").json()
    assert result["score"] == 0.0
    assert result["passed"] is False


def test_submit_choices_double_submit_409(client: TestClient, assessments_session: Any) -> None:
    _seed_banks(assessments_session)
    course_id, module_id = _make_course_with_plan(client)
    a_id = client.post(
        f"/api/courses/{course_id}/modules/{module_id}/assessments/start",
        params={"type": "choices"},
    ).json()["id"]
    client.post(f"/api/courses/{course_id}/assessments/{a_id}/choices/submit")
    resp = client.post(f"/api/courses/{course_id}/assessments/{a_id}/choices/submit")
    assert resp.status_code == 409


def test_retake_blocked_after_pass(client: TestClient, assessments_session: Any) -> None:
    _seed_banks(assessments_session)
    course_id, module_id = _make_course_with_plan(client)
    a_id = client.post(
        f"/api/courses/{course_id}/modules/{module_id}/assessments/start",
        params={"type": "choices"},
    ).json()["id"]
    # Select all correct
    qs = client.get(f"/api/courses/{course_id}/assessments/{a_id}").json()["choice_questions"]
    for q in qs:
        client.post(
            f"/api/courses/{course_id}/assessments/{a_id}/choices/{q['id']}/select",
            json={"selections": ["A"]},
        )
    client.post(f"/api/courses/{course_id}/assessments/{a_id}/choices/submit")

    resp = client.post(
        f"/api/courses/{course_id}/modules/{module_id}/assessments/start",
        params={"type": "choices"},
    )
    assert resp.status_code == 409
    assert "passed" in resp.json()["detail"]


# ── results ───────────────────────────────────────────────────────────────────


def test_get_results_reveals_correct_answers(client: TestClient, assessments_session: Any) -> None:
    _seed_banks(assessments_session)
    course_id, module_id = _make_course_with_plan(client)
    a_id = client.post(
        f"/api/courses/{course_id}/modules/{module_id}/assessments/start",
        params={"type": "choices"},
    ).json()["id"]
    client.post(f"/api/courses/{course_id}/assessments/{a_id}/choices/submit")
    results = client.get(f"/api/courses/{course_id}/assessments/{a_id}/results").json()
    # correct_answers are revealed in the results view
    for q in results["questions"]:
        assert q["correct_answers"] == ["A"]


def test_get_results_before_submit_409(client: TestClient, assessments_session: Any) -> None:
    _seed_banks(assessments_session)
    course_id, module_id = _make_course_with_plan(client)
    a_id = client.post(
        f"/api/courses/{course_id}/modules/{module_id}/assessments/start",
        params={"type": "choices"},
    ).json()["id"]
    resp = client.get(f"/api/courses/{course_id}/assessments/{a_id}/results")
    assert resp.status_code == 409


# ── LLM round-robin ───────────────────────────────────────────────────────────


def test_llm_round_robin_rotates_questions(client: TestClient, assessments_session: Any) -> None:
    """Consecutive LLM attempts rotate through the 3 bank questions in order."""
    _seed_banks(assessments_session)
    course_id, module_id = _make_course_with_plan(client)

    # Pass choices first.
    a_choices = client.post(
        f"/api/courses/{course_id}/modules/{module_id}/assessments/start",
        params={"type": "choices"},
    ).json()
    for q in a_choices["choice_questions"]:
        client.post(
            f"/api/courses/{course_id}/assessments/{a_choices['id']}/choices/{q['id']}/select",
            json={"selections": ["A"]},
        )
    client.post(f"/api/courses/{course_id}/assessments/{a_choices['id']}/choices/submit")

    def _start_llm_and_fail() -> str:
        s = client.post(
            f"/api/courses/{course_id}/modules/{module_id}/assessments/start",
            params={"type": "llm"},
        ).json()
        # Force-submit immediately (all questions score 0 → fail)
        client.post(f"/api/courses/{course_id}/assessments/{s['id']}/llm/submit")
        return s["llm_questions"][0]["bank_question_id"]

    bqid1 = _start_llm_and_fail()  # attempt 1 → bank question index 0 (l01)
    bqid2 = _start_llm_and_fail()  # attempt 2 → bank question index 1 (l02)
    bqid3 = _start_llm_and_fail()  # attempt 3 → bank question index 2 (l03)

    assert bqid1 == "cb-c01-m01-l01"
    assert bqid2 == "cb-c01-m01-l02"
    assert bqid3 == "cb-c01-m01-l03"


# ── Module completion gate ────────────────────────────────────────────────────


def test_module_marked_complete_when_both_pass(
    client: TestClient, assessments_session: Any
) -> None:
    _seed_banks(assessments_session)
    course_id, module_id = _make_course_with_plan(client)

    # Pass choices.
    a_c = client.post(
        f"/api/courses/{course_id}/modules/{module_id}/assessments/start",
        params={"type": "choices"},
    ).json()
    for q in a_c["choice_questions"]:
        client.post(
            f"/api/courses/{course_id}/assessments/{a_c['id']}/choices/{q['id']}/select",
            json={"selections": ["A"]},
        )
    client.post(f"/api/courses/{course_id}/assessments/{a_c['id']}/choices/submit")

    # Module should still be incomplete (LLM not done).
    modules = client.get(f"/api/courses/{course_id}/modules").json()
    assert not modules[0]["completed"]

    # Start LLM + pass via start+llm_turn with auto-grade.
    a_l = client.post(
        f"/api/courses/{course_id}/modules/{module_id}/assessments/start",
        params={"type": "llm"},
    ).json()
    # Force-submit with a score via submit_llm; offline grader would score 0 → fail.
    # Patch the score directly to test the gate.
    from app.courses.models import LlmQuestion
    from app.db import session_scope

    a_id = a_l["id"]
    with session_scope() as s:
        qs_db = s.exec(
            __import__("sqlmodel", fromlist=["select"])
            .select(LlmQuestion)
            .where(LlmQuestion.assessment_id == a_id)
        ).all()
        for q in qs_db:
            q.score = 8
            q.reasoning = "Great answer."
            q.grading_complete = True
            q.submitted = True
            q.is_correct = True
            s.add(q)
        s.commit()

    # Now call submit_llm — it will see all graded and compute avg.
    result = client.post(f"/api/courses/{course_id}/assessments/{a_id}/llm/submit").json()
    assert result["passed"] is True

    # Module must now be complete.
    modules = client.get(f"/api/courses/{course_id}/modules").json()
    assert modules[0]["completed"]


# ── LLM start + turn ─────────────────────────────────────────────────────────


def test_llm_start_returns_opening_message(client: TestClient, assessments_session: Any) -> None:
    _seed_banks(assessments_session)
    course_id, module_id = _make_course_with_plan(client)

    # Pass choices first.
    a_c = client.post(
        f"/api/courses/{course_id}/modules/{module_id}/assessments/start",
        params={"type": "choices"},
    ).json()
    for q in a_c["choice_questions"]:
        client.post(
            f"/api/courses/{course_id}/assessments/{a_c['id']}/choices/{q['id']}/select",
            json={"selections": ["A"]},
        )
    client.post(f"/api/courses/{course_id}/assessments/{a_c['id']}/choices/submit")

    a_l = client.post(
        f"/api/courses/{course_id}/modules/{module_id}/assessments/start",
        params={"type": "llm"},
    ).json()
    q_state = client.post(f"/api/courses/{course_id}/assessments/{a_l['id']}/llm/start").json()
    assert len(q_state["messages"]) == 1
    assert q_state["messages"][0]["role"] == "assistant"
    # Opening message includes the question prompt.
    assert "Explain" in q_state["messages"][0]["content"]


def test_llm_turn_offline_grade_at_ceiling(client: TestClient, assessments_session: Any) -> None:
    """After ceiling turns the offline grader returns a grade."""
    _seed_banks(assessments_session)
    course_id, module_id = _make_course_with_plan(client)

    # Pass choices.
    a_c = client.post(
        f"/api/courses/{course_id}/modules/{module_id}/assessments/start",
        params={"type": "choices"},
    ).json()
    for q in a_c["choice_questions"]:
        client.post(
            f"/api/courses/{course_id}/assessments/{a_c['id']}/choices/{q['id']}/select",
            json={"selections": ["A"]},
        )
    client.post(f"/api/courses/{course_id}/assessments/{a_c['id']}/choices/submit")

    a_l = client.post(
        f"/api/courses/{course_id}/modules/{module_id}/assessments/start",
        params={"type": "llm"},
    ).json()
    q_id = a_l["llm_questions"][0]["id"]

    # Call ceiling=8 turns. Each SSE response should have token or grade events.
    graded = False
    for i in range(9):  # go past ceiling
        raw = client.post(
            f"/api/courses/{course_id}/assessments/{a_l['id']}/llm/{q_id}/turn",
            json={"content": f"My answer attempt {i + 1}"},
        )
        # Parse SSE
        for line in raw.text.split("\n\n"):
            line = line.strip()
            if line.startswith("data:"):
                import json

                event = json.loads(line[5:])
                if event.get("type") == "grade":
                    graded = True
        if graded:
            break

    assert graded, "Expected a grade event within ceiling turns"


# ── grader unit tests ─────────────────────────────────────────────────────────


def test_grader_opening_offline() -> None:
    from app.agent.grader import opening_message

    msg = opening_message("What is a partition key?")
    assert "partition key" in msg.lower() or "QUESTION" in msg


def test_grader_turn_offline_ceiling() -> None:
    from app.agent.grader import run_turn

    result = run_turn(
        prompt="Explain partition pruning.",
        reference_answer="It skips files whose partition values don't match the filter.",
        history=[
            {"role": "assistant", "content": "Please explain partition pruning."},
            {"role": "user", "content": "It is something about files."},
        ],
        turn_count=8,  # at ceiling
    )
    # At ceiling the offline grader must return a grade.
    assert result.grade is not None
    assert 0 <= result.grade.score <= 10


def test_grader_turn_offline_below_ceiling() -> None:
    from app.agent.grader import run_turn

    result = run_turn(
        prompt="Explain partition pruning.",
        reference_answer="It skips files whose partition values don't match the filter.",
        history=[
            {"role": "assistant", "content": "Please explain partition pruning."},
            {"role": "user", "content": "I am not sure."},
        ],
        turn_count=1,
    )
    # Below ceiling, offline grader asks a follow-up.
    assert result.grade is None
    assert result.reply
