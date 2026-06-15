"""Response DTOs for the Manager Insights surface.

All shapes are aggregate-only: counts, averages, and rates over a team, never a
named individual's figures. Mirrors the project convention of keeping request /
response DTOs (plain ``BaseModel``) separate from the Work IQ domain models.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RiskArea = Literal["exam_readiness", "engagement"]
RiskSeverity = Literal["high", "medium", "low"]


class ReadinessBreakdown(BaseModel):
    """Team certification-readiness distribution, derived from real platform activity.

    GO = the learner has completed at least one course in their certification path
    (every module passed); CONDITIONAL = started but no course finished yet; NOT_YET =
    no activity. Computed live from ``athenaeum.db`` — updates as learners progress.
    """

    go: int = Field(ge=0)
    conditional: int = Field(ge=0)
    not_yet: int = Field(ge=0)
    total: int = Field(ge=0)


class CohortReadiness(BaseModel):
    """Readiness for one sub-cohort of the team (e.g. a seniority band)."""

    label: str
    go: int = Field(ge=0)
    conditional: int = Field(ge=0)
    not_yet: int = Field(ge=0)
    total: int = Field(ge=0)


class CertTargetProgress(BaseModel):
    """Progress toward one of the team's certification targets.

    The target (which cert, which quarter, who is aiming for it) is an org plan; the
    ``ready_count`` is real — members aiming at this cert who have reached GO readiness
    from actual course completion.
    """

    vertical: str
    cert: str
    target_quarter: str
    member_count: int = Field(ge=0, description="Members whose target cert is this one")
    ready_count: int = Field(ge=0, description="Of those, members at GO readiness")


class PlatformEngagement(BaseModel):
    """Real in-app assessment activity for the team (Source 2; athenaeum.db).

    Honest empty state: when nobody has taken an assessment yet, ``has_activity``
    is False and the counts are zero — itself a valid manager signal.
    """

    members_total: int = Field(default=0, ge=0)
    members_active: int = Field(
        default=0, ge=0, description="Members with >=1 graded assessment attempt"
    )
    assessments_attempted: int = Field(default=0, ge=0)
    assessments_passed: int = Field(default=0, ge=0)
    modules_with_a_pass: int = Field(
        default=0, ge=0, description="Distinct modules with >=1 passed attempt"
    )
    modules_completed: int = Field(
        default=0, ge=0, description="Modules with BOTH quiz and oral passed (true completion)"
    )
    pass_rate: float | None = Field(default=None, description="passed/attempted, None if none yet")
    has_activity: bool = Field(default=False)


class RiskFlag(BaseModel):
    """One aggregate, name-free risk surfaced to the manager."""

    area: RiskArea
    severity: RiskSeverity
    title: str
    detail: str = Field(description="Aggregate phrasing only — never names an individual")


class TeamInsights(BaseModel):
    """The manager's at-a-glance team view — real platform activity only.

    Every figure is derived live from the team's actual course and assessment activity
    in ``athenaeum.db`` and updates as learners progress. No static org metrics.
    """

    team_id: str
    team_name: str
    manager_codename: str
    member_count: int = Field(ge=0)
    readiness: ReadinessBreakdown
    by_seniority: list[CohortReadiness] = Field(default_factory=list)
    cert_targets: list[CertTargetProgress] = Field(default_factory=list)
    engagement: PlatformEngagement
    risks: list[RiskFlag] = Field(default_factory=list)
    disclaimer: str = Field(
        default="Aggregate, team-level only — no personal data. Live from real activity.",
    )


class ManagerChatTurn(BaseModel):
    """One prior turn passed back for multi-turn context."""

    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class ManagerChatIn(BaseModel):
    """A manager's chat turn, with optional recent history for follow-up context."""

    content: str = Field(min_length=1, max_length=8000)
    history: list[ManagerChatTurn] = Field(default_factory=list)
