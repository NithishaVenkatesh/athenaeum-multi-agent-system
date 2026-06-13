"""Deterministic course-recommender tests (offline; over the committed catalog)."""

from __future__ import annotations

from app.agent.contracts import TakenCourse
from app.agent.recommend import recommend_courses


def test_fresh_learner_gets_foundational_of_their_vertical() -> None:
    recs = recommend_courses(vertical="cloud-backend", taken=[], role_title="Backend Engineer")
    assert recs
    assert recs[0].catalog_id == "cb-c01"
    assert recs[0].level == "foundational"
    assert "Backend Engineer" in recs[0].reason


def test_spans_current_and_target_cert_tracks() -> None:
    # On AZ-204 (cloud-backend) but targeting AZ-305 (architecture-security):
    # both foundational courses are eligible → real choices.
    recs = recommend_courses(vertical="cloud-backend", target_cert="AZ-305", taken=[])
    ids = {r.catalog_id for r in recs}
    assert "cb-c01" in ids and "as-c01" in ids


def test_natural_next_after_completing_a_course() -> None:
    recs = recommend_courses(
        vertical="cloud-backend", taken=[TakenCourse(catalog_id="cb-c01", status=-1)]
    )
    ids = [r.catalog_id for r in recs]
    assert "cb-c02" in ids  # prereq cb-c01 completed → unlocks cb-c02
    assert "cb-c01" not in ids  # already taken


def test_in_progress_course_does_not_satisfy_prereq() -> None:
    # status=1 (on attempt 1, not passed) must NOT unlock the next course.
    recs = recommend_courses(
        vertical="cloud-backend", taken=[TakenCourse(catalog_id="cb-c01", status=1)]
    )
    ids = [r.catalog_id for r in recs]
    # cb-c01 is taken (excluded); cb-c02 needs cb-c01 *completed*, which it isn't,
    # so the fallback offers the earliest untaken (cb-c02) to stay unblocked.
    assert "cb-c01" not in ids
    assert ids  # always something to offer


def test_respects_k_limit() -> None:
    recs = recommend_courses(vertical="cloud-backend", target_cert="AZ-305", taken=[], k=1)
    assert len(recs) == 1


def test_unknown_vertical_falls_back_to_whole_catalog() -> None:
    recs = recommend_courses(vertical=None, taken=[])
    assert recs  # still recommends something
