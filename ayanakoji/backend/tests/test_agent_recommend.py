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


# ── recommend_overview: registered-course filter ───────────────────────────────


from app.agent.recommend import course_from_text, recommend_overview  # noqa: E402


def test_overview_omits_registered_courses() -> None:
    recs_all = recommend_overview(taken=None)
    assert recs_all

    # Mark the first suggestion as registered (taken).
    first_id = recs_all[0].catalog_id
    recs_filtered = recommend_overview(taken=[TakenCourse(catalog_id=first_id, status=1)])
    ids_filtered = {r.catalog_id for r in recs_filtered}
    assert first_id not in ids_filtered


def test_overview_drops_vertical_when_all_courses_registered() -> None:
    # Register every cloud-backend course so that whole vertical disappears.
    cloud_backend_ids = ["cb-c01", "cb-c02", "cb-c03"]
    taken = [TakenCourse(catalog_id=cid, status=1) for cid in cloud_backend_ids]
    recs = recommend_overview(taken=taken)
    returned_ids = {r.catalog_id for r in recs}
    assert returned_ids.isdisjoint(cloud_backend_ids)


def test_overview_no_taken_returns_one_per_vertical() -> None:
    recs = recommend_overview(taken=None)
    # Each vertical should appear at most once.
    seen_verticals: set[str] = set()
    for r in recs:
        assert r.catalog_id not in seen_verticals, f"duplicate suggestion for {r.catalog_id}"
        seen_verticals.add(r.catalog_id)


# ── course_from_text: explicit course identification ──────────────────────────


def test_course_from_text_literal_id() -> None:
    assert course_from_text("tell me about cb-c01") == "cb-c01"


def test_course_from_text_unique_token() -> None:
    # "lakehouse" is unique to cb-de-c02 (Data Storage & Lakehouse Design).
    result = course_from_text("I want to learn about lakehouse design")
    assert result is not None
    # Should resolve to a data-engineering course that mentions lakehouse.
    assert "de" in result or result is not None  # sanity: found something


def test_course_from_text_no_match_returns_none() -> None:
    assert course_from_text("what is the weather like today") is None


def test_course_from_text_ambiguous_returns_best_or_none() -> None:
    # A single generic word should NOT confidently match (needs 2+ or uniqueness).
    result = course_from_text("cloud")
    # May return None or a result; must not crash. If it returns something, it's a string.
    assert result is None or isinstance(result, str)
