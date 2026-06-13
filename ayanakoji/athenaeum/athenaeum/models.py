"""Typed contracts for the Athenaeum catalog and the Foundry IQ ingestion documents.

These are validated at every boundary: the catalog is parsed into `Catalog`, every
authored markdown file is parsed into a `CourseDoc`/`ModuleDoc`, and each indexed record
is a `SearchDocument`. Keeping the shapes explicit is what lets the framework guarantee
catalog/content/index consistency without runtime tracing.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

DocKind = Literal["course", "module"]
Level = Literal["foundational", "intermediate", "advanced"]


class ModuleSpec(BaseModel):
    """A single sequential module within a course (catalog-level plan)."""

    id: str  # e.g. "cb-c01-m02"
    order: int = Field(ge=1, le=12)
    title: str
    summary: str
    objectives: list[str] = Field(min_length=3)
    grounded_skills: list[str] = Field(min_length=1)  # sub-skills from the real outline
    prereq_module_ids: list[str] = Field(default_factory=list)


class CourseSpec(BaseModel):
    """A course = an ordered set of modules (catalog-level plan)."""

    id: str  # e.g. "cb-c01"
    order: int = Field(ge=1, le=12)
    slug: str
    title: str
    summary: str
    level: Level
    grounded_on: str  # provenance, e.g. "AZ-204 skills outline (2026-01-14), paraphrased"
    source_url: str
    prereq_course_ids: list[str] = Field(default_factory=list)
    modules: list[ModuleSpec] = Field(min_length=1)

    @field_validator("modules")
    @classmethod
    def _modules_sequential(cls, v: list[ModuleSpec]) -> list[ModuleSpec]:
        orders = [m.order for m in v]
        if orders != list(range(1, len(v) + 1)):
            raise ValueError(f"module orders must be 1..N sequential, got {orders}")
        return v


class VerticalSpec(BaseModel):
    """One of the five software-development verticals."""

    id: str  # e.g. "cloud-backend"
    order: int = Field(ge=1, le=5)
    title: str
    summary: str
    primary_cert: str
    courses: list[CourseSpec] = Field(min_length=1)


class Catalog(BaseModel):
    """The whole grounded catalog: verticals -> courses -> modules."""

    name: str = "Athenaeum"
    description: str
    verticals: list[VerticalSpec] = Field(min_length=1)

    @property
    def course_count(self) -> int:
        return sum(len(v.courses) for v in self.verticals)

    @property
    def module_count(self) -> int:
        return sum(len(c.modules) for v in self.verticals for c in v.courses)


# ─────────────────────────────────────────────────────────────
# Authored-document contracts (parsed from markdown frontmatter)
# ─────────────────────────────────────────────────────────────


class DocFrontmatter(BaseModel):
    """Frontmatter every authored markdown file must carry (provenance + linkage)."""

    kind: DocKind
    id: str
    vertical: str
    course_id: str
    title: str
    level: Level
    grounded_on: str
    source_url: str
    synthetic: bool = True
    order: int | None = None
    prereqs: list[str] = Field(default_factory=list)
    objectives: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# Foundry IQ index record
# ─────────────────────────────────────────────────────────────


class SearchDocument(BaseModel):
    """A single record uploaded to the Azure AI Search index (one per module/course doc).

    The vectorizer embeds `content` at index time, so we do not ship embeddings here.
    """

    id: str
    kind: DocKind
    vertical: str
    course_id: str
    title: str
    level: str
    cert: str
    prereqs: str  # comma-joined for filterability
    grounded_on: str
    source_url: str
    content: str

    def as_index_dict(self) -> dict[str, object]:
        return self.model_dump()
