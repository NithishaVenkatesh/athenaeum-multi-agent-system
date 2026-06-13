"""Work Schedule Synthesizer (build-time, offline) — master-plan §12 / build-spec §7.2.

Generates the synthetic Work IQ backend data source ``app/data/work_iq.json``:
a fictional engineering org (Helix Dynamics / Team "Atlas") of 11 personas — a
senior + junior developer in each of the five Athenaeum verticals, plus one
engineering manager — with a *hyper-realistic* Mon–Fri work week at 30-minute
resolution.

Design rules honoured:
  * Synthetic-only, no PII: fabricated identifiers (``EMP-001``, ``L-1001``,
    ``TEAM-A``); star codenames are obviously fictional (synthetic-data.md).
  * Response Fidelity (Work IQ principle): every aggregate (``meeting_hours_per_week``,
    ``focus_hours_per_week``, ``collaboration_load``) is *derived* from the timed
    calendar blocks — never hand-typed — so the schedule and the work-signal
    surface can never disagree.
  * Distribution deliberately exercises the capacity rules (master-plan §11/§13):
    >20 meeting-hour cases, focus-rich juniors, both preferred slots, plus learner
    edge cases (at-exactly-75%, hours-met-but-low-score, ready-for-next-cert, fail).

Deterministic: no RNG — the same inputs always produce byte-identical output.
The generated JSON is committed as the source of truth; this script exists for
reproducibility and provenance. Never runs in the request path.

Run:  uv run python scripts/generate_work_iq.py
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Literal, NamedTuple

# ── Constants ────────────────────────────────────────────────────────────────

SCHEMA_VERSION = "1.0.0"
TIMEZONE = "Asia/Kolkata"
WEEK_ID = "2026-W24"
WEEK_START = date(2026, 6, 8)  # Monday
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri"]

OUT_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "work_iq.json"

# Which block categories meter toward which weekly aggregate.
# meeting → meeting_hours, focus → focus_hours, collab → collaboration only, neutral → neither.
Meter = Literal["meeting", "focus", "collab", "neutral"]
CATEGORY_METER: dict[str, Meter] = {
    "standup": "meeting",
    "meeting": "meeting",
    "one_on_one": "meeting",
    "ceremony": "meeting",
    "interview": "meeting",
    "focus": "focus",
    "learning": "focus",
    "pairing": "collab",
    "code_review": "collab",
    "deploy": "collab",
    "incident": "collab",
    "on_call": "neutral",
    "lunch": "neutral",
    "admin": "neutral",
}

# Per-vertical work flavour — keeps each schedule recognisably "that discipline".
FLAVOR: dict[str, dict[str, str]] = {
    "cloud-backend": {
        "focus": "Checkout API service work (App Service / Functions)",
        "review": "API Management policy review",
        "deploy": "Backend service release",
        "design": "Service design review",
        "project": "Checkout API revamp",
    },
    "devops-platform": {
        "focus": "Release pipeline & Bicep IaC work",
        "review": "Release gate & pipeline review",
        "deploy": "Production deployment window",
        "design": "Platform reliability review",
        "project": "CD platform hardening",
    },
    "data-engineering": {
        "focus": "Lakehouse pipeline development (Fabric)",
        "review": "Data quality & lineage review",
        "deploy": "Pipeline backfill run",
        "design": "Lakehouse schema review",
        "project": "Realtime analytics rollout",
    },
    "ai-ml": {
        "focus": "Model & eval work (Azure OpenAI)",
        "review": "Model eval & safety review",
        "deploy": "Inference endpoint rollout",
        "design": "RAG architecture review",
        "project": "Document intelligence service",
    },
    "architecture-security": {
        "focus": "Architecture & threat-model work",
        "review": "Security control review",
        "deploy": "Zero-trust policy rollout",
        "design": "Landing-zone design review",
        "project": "Zero-trust migration",
    },
    "management": {
        "focus": "Roadmap & headcount planning",
        "review": "Delivery risk review",
        "deploy": "Release go/no-go",
        "design": "Org design review",
        "project": "Atlas Q2 delivery",
    },
}

VERTICALS = [
    {"id": "cloud-backend", "title": "Cloud & Backend Development", "primary_cert": "AZ-204"},
    {"id": "devops-platform", "title": "DevOps & Platform Engineering", "primary_cert": "AZ-400"},
    {"id": "data-engineering", "title": "Data Engineering & Analytics", "primary_cert": "DP-700"},
    {"id": "ai-ml", "title": "AI & Machine Learning Engineering", "primary_cert": "AI-102"},
    {
        "id": "architecture-security",
        "title": "Cloud Solution Architecture & Security",
        "primary_cert": "AZ-305",
    },
]

RECOMMENDED_HOURS = {
    "AZ-204": 20,
    "AZ-400": 25,
    "DP-700": 22,
    "AI-102": 24,
    "AZ-305": 28,
    "SC-100": 26,
}

# Programming languages per vertical (Bundle E — profile).
LANGUAGES: dict[str, list[str]] = {
    "cloud-backend": ["C#", "TypeScript", "Python"],
    "devops-platform": ["Go", "Bash", "Bicep"],
    "data-engineering": ["Python", "SQL", "Scala"],
    "ai-ml": ["Python", "SQL"],
    "architecture-security": ["C#", "Bicep", "PowerShell"],
    "management": ["Python"],
}

# Per-persona varying inputs for bundles A (learning prefs), B (work context),
# E (profile). Derived fields (study days, focus windows, summaries, switch score)
# are computed from the schedule, not listed here.
EXTRAS: dict[str, dict[str, object]] = {
    "EMP-001": {
        "level": "L5",
        "years": 7,
        "tenure": 34,
        "location": "Bengaluru",
        "employment": "full_time",
        "study_hours": 5,
        "session_min": 60,
        "modality": "hands_on_lab",
        "pace": "steady",
        "reminder": True,
        "work_mode": "hybrid",
        "after_hours": "moderate",
        "latency": 25,
        "on_call": False,
        "on_call_dates": [],
        "pto": [],
    },
    "EMP-002": {
        "level": "L3",
        "years": 2,
        "tenure": 11,
        "location": "Hyderabad",
        "employment": "full_time",
        "study_hours": 8,
        "session_min": 90,
        "modality": "video",
        "pace": "intensive",
        "reminder": True,
        "work_mode": "remote",
        "after_hours": "low",
        "latency": 12,
        "on_call": False,
        "on_call_dates": [],
        "pto": [],
    },
    "EMP-003": {
        "level": "L6",
        "years": 9,
        "tenure": 46,
        "location": "Pune",
        "employment": "full_time",
        "study_hours": 4,
        "session_min": 60,
        "modality": "hands_on_lab",
        "pace": "steady",
        "reminder": False,
        "work_mode": "hybrid",
        "after_hours": "high",
        "latency": 30,
        "on_call": True,
        "on_call_dates": ["2026-06-13", "2026-06-14"],
        "pto": [],
    },
    "EMP-004": {
        "level": "L4",
        "years": 3,
        "tenure": 14,
        "location": "Chennai",
        "employment": "contractor",
        "study_hours": 6,
        "session_min": 60,
        "modality": "hands_on_lab",
        "pace": "intensive",
        "reminder": True,
        "work_mode": "office",
        "after_hours": "low",
        "latency": 15,
        "on_call": True,
        "on_call_dates": ["2026-06-11", "2026-06-12"],
        "pto": [],
    },
    "EMP-005": {
        "level": "L5",
        "years": 6,
        "tenure": 28,
        "location": "Bengaluru",
        "employment": "full_time",
        "study_hours": 4,
        "session_min": 60,
        "modality": "reading",
        "pace": "steady",
        "reminder": False,
        "work_mode": "hybrid",
        "after_hours": "moderate",
        "latency": 22,
        "on_call": False,
        "on_call_dates": [],
        "pto": ["2026-06-19", "2026-06-20"],
    },
    "EMP-006": {
        "level": "L3",
        "years": 1,
        "tenure": 7,
        "location": "Hyderabad",
        "employment": "full_time",
        "study_hours": 6,
        "session_min": 60,
        "modality": "hands_on_lab",
        "pace": "light",
        "reminder": True,
        "work_mode": "remote",
        "after_hours": "none",
        "latency": 14,
        "on_call": False,
        "on_call_dates": [],
        "pto": [],
    },
    "EMP-007": {
        "level": "L6",
        "years": 10,
        "tenure": 40,
        "location": "Bengaluru",
        "employment": "full_time",
        "study_hours": 5,
        "session_min": 60,
        "modality": "video",
        "pace": "steady",
        "reminder": True,
        "work_mode": "hybrid",
        "after_hours": "moderate",
        "latency": 28,
        "on_call": False,
        "on_call_dates": [],
        "pto": ["2026-06-26"],
    },
    "EMP-008": {
        "level": "L4",
        "years": 2,
        "tenure": 13,
        "location": "Pune",
        "employment": "full_time",
        "study_hours": 8,
        "session_min": 90,
        "modality": "video",
        "pace": "intensive",
        "reminder": True,
        "work_mode": "remote",
        "after_hours": "low",
        "latency": 13,
        "on_call": False,
        "on_call_dates": [],
        "pto": [],
    },
    "EMP-009": {
        "level": "L6",
        "years": 12,
        "tenure": 30,
        "location": "Gurugram",
        "employment": "full_time",
        "study_hours": 5,
        "session_min": 60,
        "modality": "reading",
        "pace": "steady",
        "reminder": False,
        "work_mode": "hybrid",
        "after_hours": "high",
        "latency": 35,
        "on_call": False,
        "on_call_dates": [],
        "pto": [],
    },
    "EMP-010": {
        "level": "L4",
        "years": 3,
        "tenure": 16,
        "location": "Chennai",
        "employment": "full_time",
        "study_hours": 6,
        "session_min": 60,
        "modality": "instructor_led",
        "pace": "steady",
        "reminder": True,
        "work_mode": "office",
        "after_hours": "low",
        "latency": 16,
        "on_call": False,
        "on_call_dates": [],
        "pto": [],
    },
    "EMP-011": {
        "level": "L6",
        "years": 11,
        "tenure": 42,
        "location": "Bengaluru",
        "employment": "full_time",
        "study_hours": 2,
        "session_min": 45,
        "modality": "instructor_led",
        "pace": "light",
        "reminder": True,
        "work_mode": "hybrid",
        "after_hours": "high",
        "latency": 15,
        "on_call": False,
        "on_call_dates": [],
        "pto": [],
    },
}

# Team & delivery context (Bundle F).
TEAM_CONTEXT = {
    "sprint": {
        "number": 24,
        "name": "Sprint 24 — Atlas",
        "start": "2026-06-08",
        "end": "2026-06-12",
        "goal": "Ship the Checkout API revamp behind a feature flag and harden the CD platform.",
    },
    "okrs": [
        {
            "id": "OKR-1",
            "objective": "Raise delivery reliability",
            "key_results": [
                "Cut change-failure rate below 10%",
                "Bring p95 deploy lead time under 1 day",
            ],
            "progress": 0.6,
        },
        {
            "id": "OKR-2",
            "objective": "Grow certification coverage across the team",
            "key_results": [
                "80% of engineers GO-ready on their primary cert",
                "Each vertical has one cross-trained engineer",
            ],
            "progress": 0.45,
        },
        {
            "id": "OKR-3",
            "objective": "Protect maker time",
            "key_results": [
                "Two no-meeting mornings per week per engineer",
                "Average focus hours at or above 18/week",
            ],
            "progress": 0.3,
        },
    ],
    "cert_targets": [
        {"vertical": v["id"], "cert": v["primary_cert"], "target_quarter": "Q3 FY26"}
        for v in VERTICALS
    ],
    "capacity_policy": {
        "target_study_hours_by_seniority": {"senior": 4, "junior": 6, "manager": 2}
    },
}


# ── Persona specs (declarative; schedules are built from archetypes) ─────────


class PersonaSpec(NamedTuple):
    employee_id: str
    learner_id: str
    codename: str
    vertical: str
    seniority: Literal["senior", "junior", "manager"]
    role_title: str
    certification: str
    target_cert: str
    practice_score_avg: int
    hours_studied: int
    exam_outcome: Literal["Pass", "Fail", "In Progress"]
    preferred_learning_slot: Literal["Morning", "Afternoon"]
    meeting_load: Literal["light", "standard", "heavy", "exec"]


# Star codenames (obviously fictional). Manager = Polaris (the guiding north star).
PERSONAS: list[PersonaSpec] = [
    PersonaSpec(
        "EMP-001",
        "L-1001",
        "Vega",
        "cloud-backend",
        "senior",
        "Senior Backend Engineer",
        "AZ-204",
        "AZ-305",
        78,
        22,
        "Pass",
        "Morning",
        "heavy",
    ),
    PersonaSpec(
        "EMP-002",
        "L-1002",
        "Mira",
        "cloud-backend",
        "junior",
        "Backend Engineer I",
        "AZ-204",
        "AZ-204",
        67,
        18,
        "Fail",
        "Afternoon",
        "light",
    ),
    PersonaSpec(
        "EMP-003",
        "L-1003",
        "Rigel",
        "devops-platform",
        "senior",
        "Senior Platform Engineer",
        "AZ-400",
        "AZ-400",
        82,
        24,
        "Pass",
        "Morning",
        "heavy",
    ),
    PersonaSpec(
        "EMP-004",
        "L-1004",
        "Pollux",
        "devops-platform",
        "junior",
        "Platform Engineer I",
        "AZ-400",
        "AZ-400",
        71,
        16,
        "In Progress",
        "Afternoon",
        "standard",
    ),
    PersonaSpec(
        "EMP-005",
        "L-1005",
        "Lyra",
        "data-engineering",
        "senior",
        "Senior Data Engineer",
        "DP-700",
        "DP-700",
        74,
        20,
        "Pass",
        "Morning",
        "standard",
    ),
    PersonaSpec(
        "EMP-006",
        "L-1006",
        "Cygnus",
        "data-engineering",
        "junior",
        "Data Engineer I",
        "DP-700",
        "DP-700",
        75,
        15,
        "In Progress",
        "Afternoon",
        "light",
    ),
    PersonaSpec(
        "EMP-007",
        "L-1007",
        "Orion",
        "ai-ml",
        "senior",
        "Senior ML Engineer",
        "AI-102",
        "AZ-305",
        88,
        26,
        "Pass",
        "Morning",
        "heavy",
    ),
    PersonaSpec(
        "EMP-008",
        "L-1008",
        "Nova",
        "ai-ml",
        "junior",
        "ML Engineer I",
        "AI-102",
        "AI-102",
        62,
        25,
        "Fail",
        "Afternoon",
        "light",
    ),
    PersonaSpec(
        "EMP-009",
        "L-1009",
        "Atlas",
        "architecture-security",
        "senior",
        "Principal Architect (Security)",
        "AZ-305",
        "SC-100",
        90,
        28,
        "Pass",
        "Morning",
        "heavy",
    ),
    PersonaSpec(
        "EMP-010",
        "L-1010",
        "Sirius",
        "architecture-security",
        "junior",
        "Associate Cloud Architect",
        "AZ-305",
        "AZ-305",
        70,
        14,
        "In Progress",
        "Afternoon",
        "standard",
    ),
    PersonaSpec(
        "EMP-011",
        "L-1011",
        "Polaris",
        "management",
        "manager",
        "Engineering Manager",
        "AZ-400",
        "Engineering Leadership",
        84,
        12,
        "Pass",
        "Morning",
        "exec",
    ),
]

MANAGER_ID = "EMP-011"
TEAM_ID = "TEAM-A"


# ── Block construction ───────────────────────────────────────────────────────


class Block(NamedTuple):
    start: time
    end: time
    category: str
    title: str


def _t(hhmm: str) -> time:
    h, m = hhmm.split(":")
    return time(int(h), int(m))


def _dur_hours(b: Block) -> float:
    start = datetime.combine(date.min, b.start)
    end = datetime.combine(date.min, b.end)
    return (end - start).total_seconds() / 3600.0


def _learning_anchor(slot: str) -> tuple[time, time]:
    # Cert-study block lands in the preferred slot, inside a focus window.
    return (_t("11:00"), _t("12:00")) if slot == "Morning" else (_t("16:00"), _t("17:00"))


def _is_learning_day(spec: PersonaSpec, weekday: str) -> bool:
    # Juniors study 4 days, seniors 3 days, manager 1 day (leadership reading).
    schedule = {
        "junior": ["mon", "tue", "wed", "thu"],
        "senior": ["tue", "wed", "thu"],
        "manager": ["wed"],
    }
    return weekday in schedule[spec.seniority]


def _meeting_plan(spec: PersonaSpec, weekday: str, flavor: dict[str, str]) -> list[Block]:
    """Meetings live in the afternoon (+ a midday sync); mornings stay maker-time.

    Density is driven by ``meeting_load`` so heavy seniors/manager cross the
    >20 meeting-hour line that triggers the capacity rule (master-plan §13).
    """
    load = spec.meeting_load
    b: list[Block] = []

    if load == "exec":
        b += [
            Block(_t("10:00"), _t("11:00"), "meeting", "Leadership sync"),
            Block(_t("12:00"), _t("13:00"), "meeting", "Stakeholder / product sync"),
            Block(_t("14:00"), _t("14:30"), "one_on_one", "1:1 with engineer"),
            Block(_t("14:30"), _t("15:00"), "one_on_one", "1:1 with engineer"),
            Block(_t("15:00"), _t("16:00"), "meeting", "Cross-team delivery sync"),
            Block(_t("16:00"), _t("17:00"), "meeting", flavor["review"]),
            Block(_t("17:00"), _t("17:30"), "admin", "Roadmap & reporting"),
        ]
        if weekday == "tue":
            b.append(Block(_t("09:15"), _t("09:45"), "one_on_one", "1:1 with engineer"))
        if weekday == "thu":
            b = [x for x in b if not (x.start == _t("16:00") and x.category == "meeting")]
            b.append(Block(_t("16:00"), _t("17:00"), "interview", "Hiring panel — debrief"))
    else:
        # Common midday triage for IC roles.
        b.append(Block(_t("12:00"), _t("13:00"), "meeting", "Stakeholder / triage sync"))
        if load == "heavy":
            b += [
                Block(_t("10:00"), _t("11:00"), "meeting", "Architecture council"),
                Block(_t("14:00"), _t("15:00"), "meeting", flavor["design"]),
                Block(_t("15:00"), _t("16:00"), "meeting", "Cross-team sync"),
            ]
        elif load == "standard":
            b.append(Block(_t("14:00"), _t("15:00"), "meeting", flavor["design"]))
        else:  # light
            b = [Block(_t("12:00"), _t("12:30"), "meeting", "Team triage")]

    # Sprint ceremonies at end of day so they never collide with the study slot.
    if weekday == "mon":
        b.append(
            Block(_t("17:30"), _t("18:00"), "ceremony", f"Sprint planning — {flavor['project']}")
        )
    if weekday == "fri":
        b.append(Block(_t("17:30"), _t("18:00"), "ceremony", "Sprint review & retro"))

    # Weekly 1:1 with the manager for every IC (early, before maker-time).
    if weekday == "wed" and spec.seniority != "manager":
        b.append(Block(_t("09:15"), _t("09:45"), "one_on_one", "1:1 with manager"))

    return b


class Reservation(NamedTuple):
    minutes: int
    category: str
    title: str


def _collab_reservations(spec: PersonaSpec, weekday: str) -> list[Reservation]:
    """Mentoring / pairing / code-review — the senior↔junior collaboration fabric.

    Returned as durations; the allocator drops them into real free afternoon slots
    so they never collide with a meeting-dense day.
    """
    if spec.seniority == "manager":
        return []
    res: list[Reservation] = []
    if spec.seniority == "senior":
        res.append(Reservation(30, "code_review", "Review team pull requests"))
        if weekday in ("tue", "thu"):
            res.append(Reservation(30, "pairing", "Mentoring junior engineer"))
    else:  # junior
        res.append(Reservation(60, "pairing", "Pairing with senior engineer"))
        if weekday in ("mon", "wed"):
            res.append(Reservation(30, "code_review", "Address review feedback"))
    return res


def _ops_blocks(spec: PersonaSpec, weekday: str) -> list[Block]:
    """On-call / incident / deployment blocks (end-of-day, never collide with ceremonies).

    Keeps the ``work_context.on_call`` flag honest: an on-call persona's calendar
    actually shows the incident + handoff, and platform engineers show deploys.
    """
    extra = EXTRAS[spec.employee_id]
    is_on_call = bool(extra["on_call"])
    blocks: list[Block] = []
    if spec.vertical == "devops-platform" and weekday == "thu":
        blocks.append(Block(_t("17:30"), _t("18:00"), "deploy", "Production deployment window"))
    if is_on_call and weekday == "wed":
        blocks.append(Block(_t("17:30"), _t("18:00"), "incident", "Incident response (sev-2)"))
    if is_on_call and weekday == "fri":
        blocks.append(Block(_t("17:00"), _t("17:30"), "on_call", "On-call shift handoff"))
    return blocks


# Fillable maker-time windows. Outside lunch (13–14) & standup/admin (09:00–09:45).
_FILL_WINDOWS = [(_t("09:45"), _t("13:00")), (_t("14:00"), _t("18:00"))]
_AFTERNOON_START = 14 * 60


def _mins(t: time) -> int:
    return t.hour * 60 + t.minute


def _tm(m: int) -> time:
    return time(m // 60, m % 60)


def _free_intervals(occupied: list[Block]) -> list[list[int]]:
    """Return free [start, end] minute-intervals inside the fill windows."""
    busy = sorted((_mins(b.start), _mins(b.end)) for b in occupied)
    free: list[list[int]] = []
    for win_start, win_end in _FILL_WINDOWS:
        cursor, end = _mins(win_start), _mins(win_end)
        for bs, be in busy:
            if be <= cursor or bs >= end:
                continue
            if bs > cursor:
                free.append([cursor, min(bs, end)])
            cursor = max(cursor, be)
        if cursor < end:
            free.append([cursor, end])
    return [iv for iv in free if iv[1] > iv[0]]


def _focus_title(spec: PersonaSpec, start_min: int) -> str:
    flavor = FLAVOR[spec.vertical]
    return flavor["focus"] if start_min < _mins(_t("13:00")) else "Deep work block"


def _fill_focus(fixed: list[Block], spec: PersonaSpec, weekday: str) -> list[Block]:
    """Carve the learning hour, allocate collab into free afternoon slots, fill focus."""
    occupied = list(fixed)

    # 1. Learning is positionally fixed at the preferred-slot anchor (study days only).
    if _is_learning_day(spec, weekday):
        a_start, a_end = _learning_anchor(spec.preferred_learning_slot)
        if not _overlaps(occupied, _mins(a_start), _mins(a_end)):
            title = f"Cert study: {spec.certification} ({spec.target_cert} track)"
            occupied.append(Block(a_start, a_end, "learning", title))

    # 2. Allocate collaboration into real free afternoon slots.
    free = _free_intervals(occupied)
    for res in _collab_reservations(spec, weekday):
        slot = next(
            (iv for iv in free if iv[0] >= _AFTERNOON_START and iv[1] - iv[0] >= res.minutes),
            None,
        )
        if slot is None:
            continue
        occupied.append(Block(_tm(slot[0]), _tm(slot[0] + res.minutes), res.category, res.title))
        slot[0] += res.minutes  # consume the front of the interval

    # 3. Everything still free becomes focus / deep work.
    for gap_start, gap_end in _free_intervals(occupied):
        occupied.append(Block(_tm(gap_start), _tm(gap_end), "focus", _focus_title(spec, gap_start)))
    return occupied


def _overlaps(blocks: list[Block], start_min: int, end_min: int) -> bool:
    return any(_mins(b.start) < end_min and start_min < _mins(b.end) for b in blocks)


def _build_day(spec: PersonaSpec, weekday: str) -> list[Block]:
    """Assemble one realistic day: anchors + meetings + collab, then fill focus."""
    fixed: list[Block] = [
        Block(_t("09:00"), _t("09:15"), "standup", "Atlas daily standup"),
        Block(_t("13:00"), _t("14:00"), "lunch", "Lunch"),
    ]
    # ICs open with admin triage, except Wednesday when the manager 1:1 takes that slot.
    if spec.seniority != "manager" and weekday != "wed":
        fixed.append(Block(_t("09:15"), _t("09:45"), "admin", "Inbox & PR triage"))
    fixed += _meeting_plan(spec, weekday, FLAVOR[spec.vertical])
    fixed += _ops_blocks(spec, weekday)

    blocks = _fill_focus(fixed, spec, weekday)
    blocks.sort(key=lambda b: b.start)
    _assert_non_overlapping(spec, weekday, blocks)
    return blocks


def _assert_non_overlapping(spec: PersonaSpec, weekday: str, blocks: list[Block]) -> None:
    for prev, cur in zip(blocks, blocks[1:], strict=False):
        if cur.start < prev.end:
            raise ValueError(
                f"Overlapping blocks for {spec.employee_id} {weekday}: "
                f"{prev.title} ({prev.start}-{prev.end}) vs {cur.title} ({cur.start}-{cur.end})"
            )


# ── Aggregation ──────────────────────────────────────────────────────────────


def _week_blocks(spec: PersonaSpec) -> dict[str, list[Block]]:
    return {wd: _build_day(spec, wd) for wd in WEEKDAYS}


def _aggregate(week: dict[str, list[Block]]) -> dict[str, float]:
    meeting = focus = collab = 0.0
    for blocks in week.values():
        for b in blocks:
            meter = CATEGORY_METER[b.category]
            hours = _dur_hours(b)
            if meter == "meeting":
                meeting += hours
            elif meter == "focus":
                focus += hours
            elif meter == "collab":
                collab += hours
    return {"meeting": round(meeting, 2), "focus": round(focus, 2), "collab": round(collab, 2)}


def _collaboration_load(meeting: float, collab: float) -> str:
    total = meeting + collab
    if total >= 26:
        return "very-high"
    if total >= 20:
        return "high"
    if total >= 13:
        return "medium"
    return "low"


def _readiness(spec: PersonaSpec) -> str:
    recommended = RECOMMENDED_HOURS.get(spec.certification, 20)
    if spec.practice_score_avg >= 75 and spec.hours_studied >= recommended:
        return "GO"
    if spec.practice_score_avg >= 65:
        return "CONDITIONAL"
    return "NOT_YET"


# ── Assembly ─────────────────────────────────────────────────────────────────


def _date_for(weekday: str) -> str:
    return (WEEK_START + timedelta(days=WEEKDAYS.index(weekday))).isoformat()


# ── Bundle helpers (A learning prefs · B work context · E profile) ───────────


def _start_date(tenure_months: int) -> str:
    return (WEEK_START - timedelta(days=tenure_months * 30)).isoformat()


def _study_window(slot: str) -> dict[str, str]:
    start, end = _learning_anchor(slot)
    return {"start": start.strftime("%H:%M"), "end": end.strftime("%H:%M")}


def _focus_windows(spec: PersonaSpec) -> list[dict[str, str]]:
    """Declared maker-time windows; afternoon-slot folks get a second window."""
    if spec.seniority == "manager":
        return [{"start": "11:00", "end": "12:00"}]
    windows = [{"start": "09:45", "end": "12:00"}]
    if spec.preferred_learning_slot == "Afternoon":
        windows.append({"start": "15:30", "end": "18:00"})
    return windows


def _profile_json(spec: PersonaSpec, extra: dict[str, object]) -> dict[str, object]:
    return {
        "start_date": _start_date(int(extra["tenure"])),
        "tenure_months": extra["tenure"],
        "level_code": extra["level"],
        "years_experience": extra["years"],
        "location": extra["location"],
        "employment_type": extra["employment"],
        "languages": LANGUAGES[spec.vertical],
    }


def _learning_prefs_json(spec: PersonaSpec, extra: dict[str, object]) -> dict[str, object]:
    return {
        "preferred_study_hours_per_week": extra["study_hours"],
        "preferred_session_minutes": extra["session_min"],
        "preferred_study_days": [wd for wd in WEEKDAYS if _is_learning_day(spec, wd)],
        "study_window": _study_window(spec.preferred_learning_slot),
        "preferred_modality": extra["modality"],
        "pace": extra["pace"],
        "reminder_opt_in": extra["reminder"],
    }


def _day_summary(blocks: list[Block]) -> dict[str, object]:
    """Derived per-day rollup — the granular workload-insight signal."""
    meeting = focus = learning = collab = 0.0
    longest_focus = 0
    ordered = sorted(blocks, key=lambda b: b.start)
    for b in ordered:
        hours = _dur_hours(b)
        if CATEGORY_METER[b.category] == "meeting":
            meeting += hours
        elif CATEGORY_METER[b.category] == "collab":
            collab += hours
        if b.category == "focus":
            focus += hours
        elif b.category == "learning":
            learning += hours
        if b.category in ("focus", "learning"):
            longest_focus = max(longest_focus, round(hours * 60))
    transitions = sum(
        CATEGORY_METER[a.category] != CATEGORY_METER[c.category]
        for a, c in zip(ordered, ordered[1:], strict=False)
    )
    fragmentation = round(transitions / (len(ordered) - 1), 2) if len(ordered) > 1 else 0.0
    return {
        "meeting_hours": round(meeting, 2),
        "focus_hours": round(focus, 2),
        "learning_hours": round(learning, 2),
        "collab_hours": round(collab, 2),
        "block_count": len(ordered),
        "longest_focus_block_minutes": longest_focus,
        "fragmentation_score": fragmentation,
        "free_capacity_hours": round(focus, 2),
    }


def _work_context_json(
    spec: PersonaSpec, summaries: list[dict[str, object]], extra: dict[str, object]
) -> dict[str, object]:
    fragmentations = [float(s["fragmentation_score"]) for s in summaries]
    longest = max(int(s["longest_focus_block_minutes"]) for s in summaries)
    return {
        "work_mode": extra["work_mode"],
        "working_hours": {"start": "09:00", "end": "18:00"},
        "working_days": list(WEEKDAYS),
        "focus_windows": _focus_windows(spec),
        "on_call": {"is_on_call": extra["on_call"], "dates": extra["on_call_dates"]},
        "pto_days": extra["pto"],
        "after_hours_load": extra["after_hours"],
        "context_switch_score": round(sum(fragmentations) / len(fragmentations), 2),
        "longest_focus_block_minutes": longest,
        "response_latency_minutes": extra["latency"],
    }


def _persona_json(spec: PersonaSpec) -> dict:
    week = _week_blocks(spec)
    agg = _aggregate(week)
    recommended = RECOMMENDED_HOURS.get(spec.certification, 20)

    days = [
        {
            "day": wd,
            "date": _date_for(wd),
            "blocks": [
                {
                    "start": b.start.strftime("%H:%M"),
                    "end": b.end.strftime("%H:%M"),
                    "category": b.category,
                    "meter": CATEGORY_METER[b.category],
                    "duration_hours": round(_dur_hours(b), 2),
                    "title": b.title,
                    "collaborative": CATEGORY_METER[b.category] in ("meeting", "collab"),
                }
                for b in week[wd]
            ],
            "summary": _day_summary(week[wd]),
        }
        for wd in WEEKDAYS
    ]
    summaries = [day["summary"] for day in days]
    extra = EXTRAS[spec.employee_id]

    return {
        "employee_id": spec.employee_id,
        "learner_id": spec.learner_id,
        "codename": spec.codename,
        "team_id": TEAM_ID,
        "vertical": spec.vertical,
        "seniority": spec.seniority,
        "role_title": spec.role_title,
        "certification": spec.certification,
        "is_manager": spec.seniority == "manager",
        "manager_employee_id": None if spec.employee_id == MANAGER_ID else MANAGER_ID,
        "reports": [p.employee_id for p in PERSONAS if p.employee_id != MANAGER_ID]
        if spec.employee_id == MANAGER_ID
        else [],
        "timezone": TIMEZONE,
        "preferred_learning_slot": spec.preferred_learning_slot,
        # Bundle E — synthetic profile/identity.
        "profile": _profile_json(spec, extra),
        # Bundle A — learning preferences & cadence.
        "learning_preferences": _learning_prefs_json(spec, extra),
        # Bundle B — work context & availability.
        "work_context": _work_context_json(spec, summaries, extra),
        # Work IQ Dataset 2 surface — DERIVED from the schedule (Response Fidelity).
        "work_signals": {
            "employee_id": spec.employee_id,
            "meeting_hours_per_week": agg["meeting"],
            "focus_hours_per_week": agg["focus"],
            "preferred_learning_slot": spec.preferred_learning_slot,
            "collaboration_load": _collaboration_load(agg["meeting"], agg["collab"]),
        },
        # Learner performance — Dataset 1 surface.
        "learning": {
            "learner_id": spec.learner_id,
            "role": spec.role_title,
            "certification": spec.certification,
            "practice_score_avg": spec.practice_score_avg,
            "hours_studied": spec.hours_studied,
            "exam_outcome": spec.exam_outcome,
            "target_cert": spec.target_cert,
            "recommended_hours": recommended,
            "readiness_status": _readiness(spec),
        },
        "schedule": {"week_id": WEEK_ID, "days": days},
    }


def build_document() -> dict:
    personas = [_persona_json(spec) for spec in PERSONAS]
    return {
        "service": {
            "name": "Atlas Work IQ (synthetic)",
            "pattern": "Microsoft Work IQ",
            "description": (
                "Work-IQ-pattern read service over a synthetic engineering org. "
                "Transforms simulated work signals into agent-ready intelligence."
            ),
            "principles": [
                "Unified Surface — one read contract for people- and agent-driven use",
                "Response Fidelity — aggregates derived from the calendar, never hand-typed",
                "Multi-Protocol Runtime — REST head exposed here; A2A/MCP heads documented",
            ],
            "security_note": "Demo backend is open read-only; production parity is "
            "security-trimmed, delegated, user-scoped access honouring tenant boundaries.",
            "disclaimer": (
                "SYNTHETIC, DEMO-ONLY. Fabricated identifiers; no real people, PII, emails, "
                "or customer data. Star codenames are fictional personas, not individuals."
            ),
            "schema_version": SCHEMA_VERSION,
            "week": {
                "id": WEEK_ID,
                "start": WEEK_START.isoformat(),
                "end": _date_for("fri"),
                "weekdays": WEEKDAYS,
                "timezone": TIMEZONE,
            },
        },
        "org": {
            "id": "ORG-HELIX",
            "name": "Helix Dynamics",
            "product": "Helix Cloud Platform",
            "department": "Platform Engineering",
            "teams": [
                {
                    "id": TEAM_ID,
                    "name": "Atlas",
                    "manager_employee_id": MANAGER_ID,
                    "member_employee_ids": [p.employee_id for p in PERSONAS],
                    # Bundle F — team & delivery context.
                    "sprint": TEAM_CONTEXT["sprint"],
                    "okrs": TEAM_CONTEXT["okrs"],
                    "cert_targets": TEAM_CONTEXT["cert_targets"],
                    "capacity_policy": TEAM_CONTEXT["capacity_policy"],
                }
            ],
        },
        "verticals": VERTICALS,
        "personas": personas,
    }


def main() -> None:
    doc = build_document()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    n_personas = len(doc["personas"])
    n_blocks = sum(len(day["blocks"]) for p in doc["personas"] for day in p["schedule"]["days"])
    print(f"Wrote {OUT_PATH.relative_to(OUT_PATH.parents[2])}")
    print(f"  personas: {n_personas}  |  calendar blocks: {n_blocks}")


if __name__ == "__main__":
    main()
