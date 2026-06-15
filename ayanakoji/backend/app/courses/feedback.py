"""Resolve which test an in-chat feedback ask is about, scoped to one course.

The pipeline is pure of the DB, so the courses layer resolves the target here and
hands the answer inputs to the FEEDBACK dispatch as a :class:`FeedbackResolution`.
Resolution order: a cross-course mention redirects; otherwise a pinned follow-up
keeps the same test; otherwise the named module's miss, then the course's most
recent miss; nothing failed yields ``none``. Every read is course-scoped, so a chat
can only ever surface its own course's tests.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from app.agent.contracts import FeedbackResolution
from app.catalog.content import get_module_content
from app.courses.models import Assessment, Course
from app.courses.repository import CourseRepository

# Structural / generic words carry no course or module identity, so they never count
# as a match signal (else "your quiz" would match every module).
_STOPWORDS = frozenset(
    {
        "module",
        "modules",
        "lesson",
        "intro",
        "introduction",
        "basics",
        "basic",
        "deep",
        "dive",
        "overview",
        "fundamentals",
        "fundamental",
        "getting",
        "started",
        "part",
        "advanced",
        "beginner",
        "essentials",
        "essential",
        "core",
        "concepts",
        "concept",
        "guide",
        "course",
        "exam",
        "test",
        "quiz",
        "assessment",
        "oral",
        "with",
        "the",
        "and",
        "for",
        "your",
        "azure",
    }
)


def feedback_performance(repo: CourseRepository, assessment: Assessment, type: str) -> str:
    """A readable summary of what the learner actually got wrong, for the tutor prompt.

    The feedback request is first-party (the learner took this test), so we hand the
    model the real per-question outcome instead of a bare natural-language question
    that the topic gate would reject as ungrounded.
    """
    if type == "choices":
        wrong = [q for q in repo.list_choice_questions(assessment.id) if q.is_correct is False]
        if not wrong:
            return "You answered every question correctly."
        lines = [
            f'- "{q.prompt}" You chose: {", ".join(q.learner_choice or []) or "nothing"}. '
            f"Correct: {', '.join(q.correct_answers)}."
            for q in wrong
        ]
        return "Questions you missed:\n" + "\n".join(lines)
    lines = [
        f'- "{q.prompt}" Examiner note: {q.reasoning or "n/a"} (scored {q.score}/10).'
        for q in repo.list_llm_questions(assessment.id)
    ]
    return "Your oral answers:\n" + "\n".join(lines)


def _significant_words(title: str) -> set[str]:
    """Distinctive content words of a title (drops short/structural words)."""
    return {w for w in re.findall(r"[a-z]+", title.lower()) if len(w) >= 4 and w not in _STOPWORDS}


def _match_in_course_module(text: str, modules: list[dict[str, Any]]) -> str | None:
    """The module in THIS course the message names, by distinctive-word overlap."""
    text_words = set(re.findall(r"[a-z]+", text.lower()))
    best_id: str | None = None
    best_score = 0
    for m in modules:
        score = len(_significant_words(str(m.get("title", ""))) & text_words)
        if score > best_score:
            best_id, best_score = str(m.get("module_id")), score
    return best_id


def _match_other_course(text: str, other_course_titles: Iterable[str]) -> str | None:
    """An OTHER course of the learner's the message names (→ redirect to its chat)."""
    text_words = set(re.findall(r"[a-z]+", text.lower()))
    for title in other_course_titles:
        if _significant_words(title) & text_words:
            return title
    return None


def _latest_completed(repo: CourseRepository, course_id: str, module_id: str) -> Assessment | None:
    """The named module's most recently submitted attempt of any type (passed or not)."""

    def _at(a: Assessment) -> datetime:
        assert a.completed_at is not None  # guarded by the filter below
        return a.completed_at

    done = [
        a for a in repo.list_module_assessments(course_id, module_id) if a.completed_at is not None
    ]
    return max(done, key=_at) if done else None


def _answer_resolution(
    repo: CourseRepository, course: Course, assessment: Assessment, this_title: str
) -> FeedbackResolution:
    """Build the grounded answer inputs for a resolved assessment."""
    module_id = assessment.module_id
    mod = repo.get_module(course.id, module_id) if module_id else None
    module_title = mod.title if mod else (module_id or "this module")
    content = get_module_content(module_id) if module_id else None
    material = (content.body[:1600] if content else "") or module_title
    return FeedbackResolution(
        kind="answer",
        module_id=module_id,
        module_title=module_title,
        type=assessment.type,
        material=material,
        performance=feedback_performance(repo, assessment, assessment.type),
        score=assessment.score,
        passed=assessment.passed,
        this_course_title=this_title,
    )


def resolve_feedback_target(
    repo: CourseRepository,
    course: Course,
    text: str,
    *,
    modules: list[dict[str, Any]],
    other_course_titles: Iterable[str],
    active: dict[str, Any] | None,
) -> FeedbackResolution:
    """Resolve an in-chat feedback ask to a concrete test, a redirect, or nothing."""
    this_title = course.chat_name
    named = _match_in_course_module(text, modules)

    # A test on another of the learner's courses belongs to that course's chat.
    if named is None:
        other = _match_other_course(text, other_course_titles)
        if other is not None:
            return FeedbackResolution(
                kind="redirect", other_course_title=other, this_course_title=this_title
            )

    # Pinned follow-up: keep grounding on the same test unless a different module was named.
    if active and named is None:
        pinned = repo.latest_assessment(
            course.id, str(active.get("module_id") or ""), str(active.get("type") or "")
        )
        if pinned is not None and pinned.completed_at is not None:
            return _answer_resolution(repo, course, pinned, this_title)

    # The failed test: the named module's miss, else this course's most recent miss.
    failed = repo.latest_failed_assessment(course.id, module_id=named)
    if failed is None and named is not None:
        # Named a module with no failed attempt: fall back to its latest completed attempt.
        failed = _latest_completed(repo, course.id, named)
    if failed is None:
        return FeedbackResolution(kind="none", this_course_title=this_title)
    return _answer_resolution(repo, course, failed, this_title)
