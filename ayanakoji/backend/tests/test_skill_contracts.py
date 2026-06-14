from __future__ import annotations

from app.agent.contracts import SkillGateRequestEvent


def test_skill_gate_request_defaults() -> None:
    e = SkillGateRequestEvent(catalog_id="de-c01", title="Data Eng", prompt="New here?")
    dumped = e.model_dump(mode="json")
    assert dumped["type"] == "skill_gate_request"
    assert dumped["options"] == ["fresher", "assessment"]
    assert dumped["catalog_id"] == "de-c01"
