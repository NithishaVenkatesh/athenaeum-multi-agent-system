"""Load and flatten the Athenaeum course catalog (read-only).

The catalog ships in the sibling ``athenaeum`` package; the path is resolved
relative to this file by default and can be overridden with
``ATHENAEUM_CATALOG_PATH``. Results are cached per resolved path.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.catalog.models import CatalogCourse
from app.config import Settings, get_settings


def default_catalog_path() -> Path:
    """In-repo default: ``ayanakoji/athenaeum/content/_catalog.json``."""
    # loader.py -> catalog -> app -> backend -> ayanakoji
    return Path(__file__).resolve().parents[3] / "athenaeum" / "content" / "_catalog.json"


def _resolve_path(settings: Settings | None) -> Path:
    settings = settings or get_settings()
    if settings.athenaeum_catalog_path:
        return Path(settings.athenaeum_catalog_path)
    return default_catalog_path()


@lru_cache(maxsize=4)
def _load(path_str: str) -> tuple[CatalogCourse, ...]:
    data = json.loads(Path(path_str).read_text(encoding="utf-8"))
    courses: list[CatalogCourse] = []
    for vertical in data["verticals"]:
        for course in vertical["courses"]:
            courses.append(
                CatalogCourse(
                    id=course["id"],
                    slug=course["slug"],
                    title=course["title"],
                    summary=course["summary"],
                    level=course["level"],
                    vertical=vertical["id"],
                    vertical_title=vertical["title"],
                    primary_cert=vertical.get("primary_cert", ""),
                )
            )
    return tuple(courses)


def get_catalog(settings: Settings | None = None) -> list[CatalogCourse]:
    """All catalog courses, flattened across verticals."""
    return list(_load(str(_resolve_path(settings))))


def get_course(course_id: str, settings: Settings | None = None) -> CatalogCourse | None:
    """Look up one course by id, or ``None`` if it is not in the catalog."""
    return next((c for c in get_catalog(settings) if c.id == course_id), None)


def is_valid_course_id(course_id: str, settings: Settings | None = None) -> bool:
    """True only for ids present in the catalog (used to validate course links)."""
    return get_course(course_id, settings) is not None
