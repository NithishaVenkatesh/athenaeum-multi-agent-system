"""Typed view of the Athenaeum course catalog.

A flattened, read-only projection of ``athenaeum/content/_catalog.json`` — the
authoritative list a course chat's ``course_id`` is restricted to. Module-level
detail in the source file is intentionally dropped here (``extra="ignore"``);
this surface only needs what the chooser and validation use.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CatalogCourse(BaseModel):
    """One Athenaeum course, flattened with its owning vertical."""

    model_config = ConfigDict(frozen=True)

    id: str
    slug: str
    title: str
    summary: str
    level: str
    vertical: str
    vertical_title: str
    primary_cert: str
