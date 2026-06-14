"""Live SSE client for the Athenaeum chat API (stdlib only, no extra deps).

Drives the *real* pipeline over HTTP exactly as the browser does:
``POST /api/courses`` then ``POST /api/courses/{id}/messages`` (text/event-stream).
Parses the typed event union into a :class:`Turn` the scorers can assert on.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from agent_audit.config import DEFAULT_PERSONA, DEFAULT_TIMEOUT


@dataclass
class Turn:
    """One assistant turn, parsed from the SSE stream."""

    answer: str = ""  # concatenated TokenEvent text
    phases: list[dict] = field(default_factory=list)
    blocked: str | None = None  # BlockedEvent.reason
    error: str | None = None  # ErrorEvent.message
    suggestion: dict | None = None  # SuggestionEvent {prompt, options}
    plan: dict | None = None  # PlanEvent.plan
    pace_request: dict | None = None
    skill_gate: dict | None = None
    new_chat: dict | None = None
    route: str | None = None  # DoneEvent.route
    suggested: bool = False
    raw: list[dict] = field(default_factory=list)  # every event, in order

    # ---- convenience views the scorers use --------------------------------------
    @property
    def gate_phase(self) -> dict | None:
        return next((p for p in self.phases if p.get("phase") == "injection_gate"), None)

    @property
    def router_phase(self) -> dict | None:
        return next((p for p in self.phases if p.get("phase") == "router"), None)

    @property
    def answer_phase(self) -> dict | None:
        return next((p for p in self.phases if p.get("phase") == "answer"), None)

    @property
    def sources(self) -> list[dict]:
        ap = self.answer_phase
        return ap.get("sources", []) if ap else []

    @property
    def source_refs(self) -> list[str]:
        return [s.get("ref", "") for s in self.sources]

    @property
    def source_courses(self) -> set[str]:
        # module ids look like "cb-c01-m02" → course "cb-c01".
        return {"-".join(r.split("-")[:2]) for r in self.source_refs if r}

    @property
    def visible_text(self) -> str:
        """What the learner actually sees (answer, or the terminal block/error)."""
        return self.answer or self.blocked or self.error or ""


class AthenaeumClient:
    """Thin HTTP client for one lane (base_url)."""

    def __init__(self, base_url: str, *, persona_id: str = DEFAULT_PERSONA) -> None:
        self.base_url = base_url.rstrip("/")
        self.persona_id = persona_id

    # ---- low-level ---------------------------------------------------------------
    def _post_json(self, path: str, body: dict, *, timeout: float = 30.0) -> dict:
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())

    def _patch_json(self, path: str, body: dict, *, timeout: float = 30.0) -> dict:
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="PATCH",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())

    # ---- course lifecycle --------------------------------------------------------
    def create_course(self, *, first_message: str = "hi", persona_id: str | None = None) -> str:
        data = self._post_json(
            "/api/courses",
            {"persona_id": persona_id or self.persona_id, "content": first_message},
        )
        return data["id"]

    def link_course(self, course_id: str, catalog_id: str) -> None:
        """Link a chat to a catalog course (the course-lock / in-course scenario)."""
        self._patch_json(f"/api/courses/{course_id}", {"catalog_id": catalog_id})

    def accept_course(self, course_id: str, catalog_id: str) -> None:
        self._post_json(f"/api/courses/{course_id}/accept", {"catalog_id": catalog_id})

    def set_pace(self, course_id: str, pace: str) -> None:
        self._post_json(f"/api/courses/{course_id}/pace", {"pace": pace})

    # ---- the streamed turn -------------------------------------------------------
    def send(self, course_id: str, content: str, *, timeout: float = DEFAULT_TIMEOUT) -> Turn:
        """Send one message; parse the SSE stream into a Turn.

        A 409 (pace gate) is surfaced as a Turn with ``error`` set, never raised,
        so a probe can assert on it.
        """
        req = urllib.request.Request(
            f"{self.base_url}/api/courses/{course_id}/messages",
            data=json.dumps({"content": content}).encode(),
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
            method="POST",
        )
        turn = Turn()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8", "replace").strip()
                    if not line.startswith("data: "):
                        continue
                    event = json.loads(line[6:])
                    _apply_event(turn, event)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            turn.error = f"HTTP {exc.code}: {body[:200]}"
        return turn

    # ---- one-shot helpers --------------------------------------------------------
    def ask(
        self,
        content: str,
        *,
        persona_id: str | None = None,
        catalog_id: str | None = None,
        first_message: str = "hi",
        timeout: float = DEFAULT_TIMEOUT,
    ) -> Turn:
        """Fresh chat (optionally linked to a course), one message → Turn."""
        cid = self.create_course(first_message=first_message, persona_id=persona_id)
        if catalog_id is not None:
            self.link_course(cid, catalog_id)
        return self.send(cid, content, timeout=timeout)


def _apply_event(turn: Turn, event: dict) -> None:
    turn.raw.append(event)
    etype = event.get("type")
    if etype == "token":
        turn.answer += event.get("token", "")
    elif etype == "phase":
        turn.phases.append(event.get("phase", {}))
    elif etype == "blocked":
        turn.blocked = event.get("reason")
    elif etype == "error":
        turn.error = event.get("message")
    elif etype == "suggestion":
        turn.suggestion = {"prompt": event.get("prompt"), "options": event.get("options", [])}
    elif etype == "plan":
        turn.plan = event.get("plan")
    elif etype == "pace_request":
        turn.pace_request = event
    elif etype == "skill_gate_request":
        turn.skill_gate = event
    elif etype == "new_chat":
        turn.new_chat = event
    elif etype == "done":
        turn.route = event.get("route")
        turn.suggested = bool(event.get("suggested"))
