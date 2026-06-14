"""FastAPI application entrypoint for the Athenaeum backend.

Skeleton only — no hackathon/agent logic yet. Provides liveness and a typed
``/api/ping`` contract the Next.js frontend uses to verify connectivity.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import __version__
from app.assessments.engine import init_db as assessments_init_db
from app.assessments.router import router as assessments_router
from app.catalog.router import router as catalog_router
from app.config import get_settings
from app.courses.assessment_router import router as assessment_session_router
from app.courses.router import router as courses_router
from app.db import init_db
from app.workiq.router import router as workiq_router


class HealthResponse(BaseModel):
    """Liveness payload."""

    status: str
    service: str
    version: str


class PingResponse(BaseModel):
    """Connectivity contract consumed by the frontend status indicator."""

    message: str
    service: str
    version: str
    timestamp: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create both database schemas on startup (idempotent ``create_all``)."""
    init_db()
    assessments_init_db()
    yield


def create_app() -> FastAPI:
    """Application factory — keeps construction testable and import-side-effect free."""
    settings = get_settings()
    app = FastAPI(
        title="Athenaeum Backend",
        version=__version__,
        description="Enterprise Learning Agent backend (skeleton).",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Synthetic Work IQ read service (GET-only).
    app.include_router(workiq_router)
    # Athenaeum course catalog (GET-only).
    app.include_router(catalog_router)
    # Learner workspace: courses (chats), messages, assessments.
    app.include_router(courses_router)
    # Authored per-module assessment question banks (GET-only, separate DB).
    app.include_router(assessments_router)
    # Learner assessment sessions (start, answer, grade, results).
    app.include_router(assessment_session_router)

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        """Liveness probe used by CI, orchestration, and uptime checks."""
        return HealthResponse(
            status="ok",
            service=settings.app_name,
            version=__version__,
        )

    @app.get("/api/ping", response_model=PingResponse, tags=["system"])
    def ping() -> PingResponse:
        """Round-trip endpoint the frontend calls to confirm backend connectivity."""
        return PingResponse(
            message="pong",
            service=settings.app_name,
            version=__version__,
            timestamp=datetime.now(UTC).isoformat(),
        )

    return app


app = create_app()
