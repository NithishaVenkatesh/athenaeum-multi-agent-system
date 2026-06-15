"""HTTP surface for the Manager Insights view (aggregate-only).

Two endpoints, both keyed by the manager's persona ``employee_id``:

- ``GET  /api/manager/{employee_id}/insights`` — the team dashboard payload.
- ``POST /api/manager/{employee_id}/chat``     — a guarded, grounded manager chat
  (SSE), reusing the same event protocol as the learner chat.

Access is gated by ``is_manager`` on the persona (404 if unknown, 403 if not a
manager). This is a data-correctness guard (resolve the right team, never expose
per-learner detail), not authentication — there is no login in this app.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.db import get_session
from app.manager.agent import run_manager_chat
from app.manager.schemas import ManagerChatIn, TeamInsights
from app.manager.service import build_team_insights
from app.workiq.models import Persona
from app.workiq.repository import WorkIQRepository, get_repository

router = APIRouter(prefix="/api/manager", tags=["manager"])

RepoDep = Annotated[WorkIQRepository, Depends(get_repository)]
SessionDep = Annotated[Session, Depends(get_session)]


def _require_manager(repo: WorkIQRepository, employee_id: str) -> Persona:
    """Resolve a manager persona or raise (404 unknown, 403 not a manager)."""
    persona = repo.get_persona(employee_id)
    if persona is None:
        raise HTTPException(status_code=404, detail=f"persona '{employee_id}' not found")
    if not persona.is_manager:
        raise HTTPException(
            status_code=403, detail="manager insights are only available to managers"
        )
    return persona


def _sse(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@router.get(
    "/{employee_id}/insights",
    response_model=TeamInsights,
    summary="Aggregate team insights for a manager",
)
def get_insights(employee_id: str, repo: RepoDep, session: SessionDep) -> TeamInsights:
    """Team readiness, capacity, cert-target progress, engagement, and risk flags."""
    manager = _require_manager(repo, employee_id)
    insights = build_team_insights(repo, session, manager)
    if insights is None:
        raise HTTPException(status_code=404, detail=f"team '{manager.team_id}' not found")
    return insights


@router.post("/{employee_id}/chat", summary="Ask about your team (guarded, grounded SSE)")
def post_chat(
    employee_id: str, body: ManagerChatIn, repo: RepoDep, session: SessionDep
) -> StreamingResponse:
    """Stream a guarded, aggregate-only answer about the manager's team.

    Insights are assembled up front (on the request session); the streaming body
    then runs purely over that captured snapshot, so no DB session is held open
    across the stream.
    """
    manager = _require_manager(repo, employee_id)
    insights = build_team_insights(repo, session, manager)
    if insights is None:
        raise HTTPException(status_code=404, detail=f"team '{manager.team_id}' not found")

    history = [{"role": t.role, "content": t.content} for t in body.history]

    def _events() -> Iterator[str]:
        for event in run_manager_chat(body.content, insights=insights, history=history):
            yield _sse(event.model_dump(mode="json"))

    return StreamingResponse(
        _events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
