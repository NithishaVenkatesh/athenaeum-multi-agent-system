"""FastAPI application entrypoint for the Ayanakoji backend.

Skeleton only — no hackathon/agent logic yet. Provides liveness and a typed
``/api/ping`` contract the Next.js frontend uses to verify connectivity.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import __version__
from app.config import get_settings


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


def create_app() -> FastAPI:
    """Application factory — keeps construction testable and import-side-effect free."""
    settings = get_settings()
    app = FastAPI(
        title="Ayanakoji Backend",
        version=__version__,
        description="Enterprise Learning Agent backend (skeleton).",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
