"""Load and validate the catalog + authored markdown, and project it into index documents.

This module is the integrity boundary: it guarantees that what gets pushed to Foundry IQ
matches the catalog exactly, is license-clean, and is well-formed — without any runtime
tracing. `validate()` returns a structured report; the CLI renders it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter
from pydantic import ValidationError

from athenaeum.config import get_settings
from athenaeum.models import Catalog, CourseSpec, DocFrontmatter, SearchDocument, VerticalSpec

# Telltale verbatim strings from the public MS Learn study guides. Authored content is
# original prose grounded on the *structure* of those outlines, so none of these boilerplate
# phrases should ever appear — their presence means copied source text leaked in.
LICENSE_FORBIDDEN = (
    "Skills measured as of",
    "This study guide should help you understand",
    "The bullets that follow each of the skills measured",
    "Audience profile",
    "Skills at a glance",
)


@dataclass
class ContentIssue:
    level: str  # "error" | "warning"
    where: str
    message: str


@dataclass
class ValidationReport:
    issues: list[ContentIssue] = field(default_factory=list)
    course_files: int = 0
    module_files: int = 0
    expected_courses: int = 0
    expected_modules: int = 0

    @property
    def errors(self) -> list[ContentIssue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[ContentIssue]:
        return [i for i in self.issues if i.level == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors


def load_catalog() -> Catalog:
    """Parse and validate content/_catalog.json into the typed Catalog."""
    settings = get_settings()
    raw = json.loads(Path(settings.catalog_path).read_text(encoding="utf-8"))
    return Catalog.model_validate(raw)


def _course_dir(vertical: VerticalSpec, course: CourseSpec) -> Path:
    return get_settings().content_dir / vertical.id / course.slug


def _module_file(course_dir: Path, order: int) -> Path | None:
    matches = sorted(course_dir.glob(f"module-{order:02d}-*.md"))
    return matches[0] if matches else None


def _parse_doc(path: Path) -> tuple[DocFrontmatter | None, str, list[ContentIssue]]:
    """Parse a markdown file's frontmatter into DocFrontmatter; return (fm, body, issues)."""
    issues: list[ContentIssue] = []
    try:
        post = frontmatter.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # malformed file
        return None, "", [ContentIssue("error", str(path), f"unreadable: {exc}")]
    try:
        fm = DocFrontmatter.model_validate(post.metadata)
    except ValidationError as exc:
        return None, post.content, [ContentIssue("error", str(path), f"bad frontmatter: {exc}")]
    body = post.content
    for needle in LICENSE_FORBIDDEN:
        if needle in body:
            issues.append(
                ContentIssue("error", str(path), f"possible copied MS Learn text: {needle!r}")
            )
    if not fm.synthetic:
        issues.append(ContentIssue("error", str(path), "frontmatter synthetic must be true"))
    return fm, body, issues


def validate() -> ValidationReport:
    """Full integrity check: catalog parses, every file exists, ids/order/prereqs align, clean."""
    report = ValidationReport()
    try:
        catalog = load_catalog()
    except (ValidationError, json.JSONDecodeError) as exc:
        report.issues.append(ContentIssue("error", "content/_catalog.json", f"invalid: {exc}"))
        return report

    report.expected_courses = catalog.course_count
    report.expected_modules = catalog.module_count
    all_module_ids = {
        m.id for v in catalog.verticals for c in v.courses for m in c.modules
    }
    all_course_ids = {c.id for v in catalog.verticals for c in v.courses}

    for vertical in catalog.verticals:
        for course in vertical.courses:
            cdir = _course_dir(vertical, course)
            course_md = cdir / "course.md"
            if not course_md.exists():
                report.issues.append(ContentIssue("error", str(cdir), "missing course.md"))
            else:
                report.course_files += 1
                fm, _body, issues = _parse_doc(course_md)
                report.issues.extend(issues)
                if fm and fm.id != course.id:
                    report.issues.append(
                        ContentIssue("error", str(course_md), f"id {fm.id} != catalog {course.id}")
                    )
            for module in course.modules:
                mfile = _module_file(cdir, module.order)
                if mfile is None:
                    report.issues.append(
                        ContentIssue("error", str(cdir), f"missing module order {module.order}")
                    )
                    continue
                report.module_files += 1
                fm, body, issues = _parse_doc(mfile)
                report.issues.extend(issues)
                if fm is None:
                    continue
                if fm.id != module.id:
                    report.issues.append(
                        ContentIssue("error", str(mfile), f"id {fm.id} != catalog {module.id}")
                    )
                if fm.order != module.order:
                    report.issues.append(
                        ContentIssue("error", str(mfile), f"order {fm.order} != {module.order}")
                    )
                for p in fm.prereqs:
                    if p not in all_module_ids and p not in all_course_ids:
                        report.issues.append(
                            ContentIssue("error", str(mfile), f"prereq {p!r} does not resolve")
                        )
                words = len(re.findall(r"\b\w+\b", body))
                if words < 700:
                    report.issues.append(
                        ContentIssue("warning", str(mfile), f"thin module: ~{words} words")
                    )

    if report.course_files != report.expected_courses:
        report.issues.append(
            ContentIssue(
                "error",
                "content/",
                f"course files {report.course_files} != expected {report.expected_courses}",
            )
        )
    if report.module_files != report.expected_modules:
        report.issues.append(
            ContentIssue(
                "error",
                "content/",
                f"module files {report.module_files} != expected {report.expected_modules}",
            )
        )
    return report


def build_documents() -> list[SearchDocument]:
    """Project the catalog + authored markdown into Foundry IQ index documents (1 per file).

    The full markdown body is the indexed `content` (the vectorizer embeds it); metadata
    fields come from the catalog so retrieval can filter by vertical/course/level/cert.
    """
    catalog = load_catalog()
    docs: list[SearchDocument] = []
    for vertical in catalog.verticals:
        for course in vertical.courses:
            cdir = _course_dir(vertical, course)
            # course overview
            course_md = cdir / "course.md"
            if course_md.exists():
                post = frontmatter.loads(course_md.read_text(encoding="utf-8"))
                docs.append(
                    SearchDocument(
                        id=course.id,
                        kind="course",
                        vertical=vertical.id,
                        course_id=course.id,
                        title=course.title,
                        level=course.level,
                        cert=vertical.primary_cert,
                        prereqs=",".join(course.prereq_course_ids),
                        grounded_on=course.grounded_on,
                        source_url=course.source_url,
                        content=f"# {course.title}\n\n{post.content.strip()}",
                    )
                )
            for module in course.modules:
                mfile = _module_file(cdir, module.order)
                if mfile is None:
                    continue
                post = frontmatter.loads(mfile.read_text(encoding="utf-8"))
                docs.append(
                    SearchDocument(
                        id=module.id,
                        kind="module",
                        vertical=vertical.id,
                        course_id=course.id,
                        title=module.title,
                        level=course.level,
                        cert=vertical.primary_cert,
                        prereqs=",".join(module.prereq_module_ids),
                        grounded_on=course.grounded_on,
                        source_url=course.source_url,
                        content=post.content.strip(),
                    )
                )
    return docs
