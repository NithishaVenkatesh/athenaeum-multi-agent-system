"""Skill-gap check endpoints: the pre-study, choice-only quiz that weights time.

Distinct from the post-completion assessment sessions in ``assessment_router``:
this samples 4 choice questions per module across the whole course, grades them
instantly by set-match, stores per-module fractions on the course, and writes a
``skill_result`` message into the transcript so the score survives reload. The
fresher path is the same code with a score of 0 on every module.
"""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.agent.study_plan import course_modules
from app.assessments.engine import get_session as get_assessment_session
from app.assessments.repository import AssessmentRepository
from app.catalog.loader import default_catalog_path
from app.catalog.loader import get_course as get_catalog_course
from app.config import get_settings
from app.courses.models import Course
from app.courses.repository import CourseRepository
from app.courses.schemas import (
    QUESTIONS_PER_MODULE,
    SetDeadline,
    SkillAnswer,
    SkillCheckModule,
    SkillCheckQuestion,
    SkillCheckRead,
    SkillGradeBody,
    SkillModuleScore,
    SkillResultRead,
)
from app.db import get_session

router = APIRouter(prefix="/api/courses", tags=["skill"])

SessionDep = Annotated[Session, Depends(get_session)]
AssessmentSessionDep = Annotated[Session, Depends(get_assessment_session)]


def _require_linked(repo: CourseRepository, course_id: str) -> Course:
    course = repo.get(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail=f"course '{course_id}' not found")
    if not course.catalog_id:
        raise HTTPException(status_code=409, detail="Choose a course before the skill check.")
    return course


def _modules_for(catalog_id: str) -> tuple:  # type: ignore[type-arg]
    settings = get_settings()
    path = str(settings.athenaeum_catalog_path or default_catalog_path())
    return course_modules(path, catalog_id)


@router.post(
    "/{course_id}/skill/start", response_model=SkillCheckRead, summary="Sample the skill check"
)
def start_skill_check(
    course_id: str, session: SessionDep, asmtsession: AssessmentSessionDep
) -> SkillCheckRead:
    """Sample up to 4 choice questions per module from the authored banks.

    The sample is persisted on the course (``skill_check_active``) so the open quiz
    card survives a reload / chat switch. While the skill step is unresolved a
    repeat call returns the stored sample, keeping the questions stable instead of
    reshuffling them under the learner.
    """
    repo = CourseRepository(session)
    course = _require_linked(repo, course_id)
    assert course.catalog_id is not None
    if course.skill_source is None and course.skill_check_active:
        return SkillCheckRead.model_validate(course.skill_check_active)
    a_repo = AssessmentRepository(asmtsession)
    catalog = get_catalog_course(course.catalog_id)
    out: list[SkillCheckModule] = []
    for m in _modules_for(course.catalog_id):
        choice_bank: list = []  # type: ignore[type-arg]
        for bid in a_repo.assessment_ids_for_module(m.module_id):
            bank = a_repo.get_bank(bid)
            if bank and bank.kind == "choices":
                choice_bank = a_repo.choice_questions(bank.id)
                break
        sample = random.sample(choice_bank, min(QUESTIONS_PER_MODULE, len(choice_bank)))
        out.append(
            SkillCheckModule(
                module_id=m.module_id,
                title=m.title,
                questions=[
                    SkillCheckQuestion(
                        id=q.id, prompt=q.prompt, kind=q.kind, choices=list(q.choices)
                    )
                    for q in sample
                ],
            )
        )
    result = SkillCheckRead(
        catalog_id=course.catalog_id,
        title=catalog.title if catalog else course.catalog_id,
        modules=out,
    )
    course.skill_check_active = result.model_dump(mode="json")
    repo.save(course)
    return result


@router.post(
    "/{course_id}/skill/grade", response_model=SkillResultRead, summary="Grade the skill check"
)
def grade_skill_check(
    course_id: str, body: SkillGradeBody, session: SessionDep, asmtsession: AssessmentSessionDep
) -> SkillResultRead:
    """Set-match grade per module, store fractions, and post a transcript message."""
    repo = CourseRepository(session)
    course = _require_linked(repo, course_id)
    assert course.catalog_id is not None
    a_repo = AssessmentRepository(asmtsession)
    title_by_id = {m.module_id: m.title for m in _modules_for(course.catalog_id)}

    by_module: dict[str, list[SkillAnswer]] = defaultdict(list)
    for ans in body.answers:
        by_module[ans.module_id].append(ans)

    scores: dict[str, float] = {}
    module_scores: list[SkillModuleScore] = []
    for module_id, answers in by_module.items():
        correct = 0
        for ans in answers:
            bank_q = a_repo.get_choice_question_by_id(ans.question_id)
            if bank_q is not None and set(ans.selections) == set(bank_q.correct_answers):
                correct += 1
        total = len(answers)
        fraction = round(correct / total, 4) if total else 0.0
        scores[module_id] = fraction
        module_scores.append(
            SkillModuleScore(
                module_id=module_id,
                title=title_by_id.get(module_id, module_id),
                correct=correct,
                total=total,
                fraction=fraction,
            )
        )

    course.skill_source = "assessment"
    course.skill_scores = scores
    course.skill_check_active = {}  # quiz resolved — drop the open-card payload
    repo.save(course)

    overall = round(sum(scores.values()) / len(scores), 4) if scores else 0.0
    result = SkillResultRead(
        catalog_id=course.catalog_id, overall_fraction=overall, modules=module_scores
    )
    summary = (
        f"Here's how you did across {len(module_scores)} modules "
        f"({round(overall * 100)}% overall). I'll lighten the modules you've got down and give a "
        "little more room where it's thinner. Do you have a target deadline?"
    )
    repo.append_message(
        course,
        role="assistant",
        content=summary,
        meta={"skill_result": result.model_dump(mode="json")},
    )
    return result


@router.post(
    "/{course_id}/skill/fresher",
    response_model=SkillResultRead,
    summary="Skip the check as a fresher",
)
def skill_fresher(course_id: str, session: SessionDep) -> SkillResultRead:
    """Mark the learner a fresher: score 0 on every module (same correction path)."""
    repo = CourseRepository(session)
    course = _require_linked(repo, course_id)
    assert course.catalog_id is not None
    scores = {m.module_id: 0.0 for m in _modules_for(course.catalog_id)}
    course.skill_source = "fresher"
    course.skill_scores = scores
    course.skill_check_active = {}  # skill step resolved — drop any open-card payload
    repo.save(course)
    result = SkillResultRead(
        catalog_id=course.catalog_id, overall_fraction=0.0, modules=[], fresher=True
    )
    summary = (
        "No problem, I'll treat this as a fresh start and give each module a little more room. "
        "Do you have a target deadline?"
    )
    repo.append_message(
        course,
        role="assistant",
        content=summary,
        meta={"skill_result": result.model_dump(mode="json")},
    )
    return result


@router.post("/{course_id}/deadline", status_code=204, summary="Set or clear the target deadline")
def set_deadline(course_id: str, body: SetDeadline, session: SessionDep) -> None:
    """Persist the optional target deadline onto ``plan_exam_date`` (drives overrun warning)."""
    repo = CourseRepository(session)
    course = repo.get(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail=f"course '{course_id}' not found")
    if body.deadline:
        try:
            date.fromisoformat(body.deadline)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="deadline must be ISO YYYY-MM-DD") from exc
        course.plan_exam_date = body.deadline
    else:
        course.plan_exam_date = None
    repo.save(course)
