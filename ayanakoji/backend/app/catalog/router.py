"""GET-only HTTP surface for the Athenaeum course catalog."""

from __future__ import annotations

from app.catalog.loader import get_catalog
from app.catalog.models import CatalogCourse
from fastapi import APIRouter

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("/courses", response_model=list[CatalogCourse], summary="Athenaeum courses")
def list_courses() -> list[CatalogCourse]:
    """The authoritative list of courses a chat's ``course_id`` may link to."""
    return get_catalog()
