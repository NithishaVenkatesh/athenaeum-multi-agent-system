"""The agentic study-plan scheduler: LLM tool-calling agent + deterministic build."""

from __future__ import annotations

from datetime import date

from app.agent.contracts import Pace
from app.agent.llm import ModelRouter, Provider, ToolCall
from app.agent.scheduler import SchedulerContext, build_plan_from_args, run_scheduler_agent
from app.config import Settings
from app.workiq.repository import get_repository

START = date(2026, 6, 15)


def _online() -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        offline_llm=False,
        foundry_project_endpoint="https://r.services.ai.azure.com/api/projects/p",
        azure_openai_endpoint="https://r.openai.azure.com/",
        azure_openai_api_key="real-key",
        groq_api_key="gsk_real",
    )


class FakeToolProvider:
    """Scripts complete_tools: each call pops the next (text, tool_calls) tuple."""

    name = Provider.AZURE

    def __init__(self, script: list[tuple[str, list[object]]]) -> None:
        self._script = list(script)

    def complete(self, *a: object, **k: object):  # pragma: no cover
        raise AssertionError("unused")

    def stream(self, *a: object, **k: object):  # pragma: no cover
        raise AssertionError("unused")

    def complete_tools(self, model, messages, *, tools, tool_choice, max_tokens):  # type: ignore[no-untyped-def]
        return self._script.pop(0)


def _ctx() -> SchedulerContext:
    vega = get_repository().get_persona("EMP-001")
    assert vega is not None
    return SchedulerContext(
        persona=vega, catalog_id="cb-c01", title="Compute", cert="AZ-204", today=START
    )


# ── The deterministic tool-arg mapping (pure) ────────────────────────────────────


def test_build_from_args_maps_new_constraints() -> None:
    plan, constraints = build_plan_from_args(
        _ctx(),
        {"pace": "faster", "max_session_minutes": 30},
        _online(),
    )
    assert plan is not None
    assert plan.pace is Pace.FASTER
    assert all(b.minutes <= 30 for m in plan.modules for b in m.scheduled)
    assert constraints["max_session_minutes"] == 30


def test_build_from_args_falls_back_to_baseline_when_empty() -> None:
    ctx = _ctx()
    plan, constraints = build_plan_from_args(ctx, {}, _online())
    assert plan is not None
    assert constraints["pace"] == "normal"  # baseline default
    assert constraints["start_date"] == START.isoformat()


def test_build_from_args_ignores_malformed_values() -> None:
    plan, constraints = build_plan_from_args(
        _ctx(),
        {"pace": "warp-speed", "start_date": "not-a-date", "max_session_minutes": -5},
        _online(),
    )
    assert plan is not None
    assert constraints["pace"] == "normal"  # bad enum ignored
    assert constraints["start_date"] == START.isoformat()  # bad date ignored
    assert constraints["max_session_minutes"] is None


# ── The agent loop (model drives the tool) ───────────────────────────────────────


def test_run_scheduler_agent_builds_plan_from_model_constraints() -> None:
    # The model infers "45-minute evening sessions, faster" and calls the tool.
    router = ModelRouter(
        _online(),
        azure=FakeToolProvider(
            [
                (
                    "",
                    [
                        ToolCall(
                            id="c1",
                            name="propose_plan",
                            arguments='{"pace": "faster", "max_session_minutes": 45, '
                            '"earliest_time": "18:00"}',
                        )
                    ],
                ),
                ("Here is your faster, evening-only plan.", []),
            ]
        ),
    )
    result = run_scheduler_agent(
        "make it faster, only evenings after 6pm, 45 minute sittings",
        _ctx(),
        router,
        settings=_online(),
    )
    assert result.plan is not None
    assert result.plan.pace is Pace.FASTER
    assert all(b.minutes <= 45 for m in result.plan.modules for b in m.scheduled)
    # Every session is in the evening window.
    assert all(int(s.start.split(":")[0]) >= 18 for s in result.plan.sessions)
    assert result.narration == "Here is your faster, evening-only plan."
    assert result.tier == 1
