"""Athenaeum catalog loader + endpoint."""

from __future__ import annotations

from app.catalog.loader import get_catalog, get_course, is_valid_course_id
from fastapi.testclient import TestClient

EXPECTED_IDS = {
    "cb-c01", "cb-c02", "cb-c03",
    "do-c01", "do-c02", "do-c03",
    "de-c01", "de-c02", "de-c03",
    "ai-c01", "ai-c02", "ai-c03",
    "as-c01", "as-c02", "as-c03",
}  # fmt: skip


def test_catalog_has_the_fifteen_courses() -> None:
    courses = get_catalog()
    assert len(courses) == 15
    assert {c.id for c in courses} == EXPECTED_IDS


def test_each_course_carries_vertical_and_level() -> None:
    for course in get_catalog():
        assert course.title
        assert course.vertical and course.vertical_title
        assert course.level in {"foundational", "intermediate", "advanced"}


def test_course_lookup_and_validation() -> None:
    assert is_valid_course_id("cb-c01") is True
    assert is_valid_course_id("not-a-course") is False

    course = get_course("ai-c01")
    assert course is not None
    assert course.vertical == "ai-ml"
    assert course.primary_cert == "AI-102"
    assert get_course("nope") is None


def test_catalog_endpoint_returns_fifteen(client: TestClient) -> None:
    resp = client.get("/api/catalog/courses")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 15
    assert {
        "id",
        "slug",
        "title",
        "summary",
        "level",
        "vertical",
        "vertical_title",
        "primary_cert",
    } <= set(body[0])
