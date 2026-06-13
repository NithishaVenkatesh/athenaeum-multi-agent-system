"""HTTP tests for the GET-only Work IQ surface, via the shared TestClient."""

from __future__ import annotations

from fastapi.testclient import TestClient

BASE = "/api/workiq"


def test_service_descriptor(client: TestClient) -> None:
    body = client.get(BASE).json()
    assert body["pattern"] == "Microsoft Work IQ"
    assert "synthetic" in body["disclaimer"].lower()
    assert body["week"]["weekdays"] == ["mon", "tue", "wed", "thu", "fri"]


def test_org_and_verticals(client: TestClient) -> None:
    org = client.get(f"{BASE}/org").json()
    assert org["teams"][0]["id"] == "TEAM-A"
    verticals = client.get(f"{BASE}/verticals").json()
    assert {v["id"] for v in verticals} == {
        "cloud-backend",
        "devops-platform",
        "data-engineering",
        "ai-ml",
        "architecture-security",
    }


def test_roster_and_filters(client: TestClient) -> None:
    roster = client.get(f"{BASE}/personas").json()
    assert len(roster) == 11

    filtered = client.get(f"{BASE}/personas", params={"vertical": "ai-ml", "seniority": "junior"})
    assert filtered.status_code == 200
    assert [p["codename"] for p in filtered.json()] == ["Nova"]


def test_roster_rejects_invalid_seniority(client: TestClient) -> None:
    # seniority is a Literal query param -> validation error.
    assert client.get(f"{BASE}/personas", params={"seniority": "principal"}).status_code == 422


def test_full_persona(client: TestClient) -> None:
    persona = client.get(f"{BASE}/personas/EMP-009").json()
    assert persona["codename"] == "Atlas"
    assert persona["work_signals"]["employee_id"] == "EMP-009"
    assert persona["learning"]["learner_id"] == "L-1009"
    assert len(persona["schedule"]["days"]) == 5


def test_persona_not_found(client: TestClient) -> None:
    response = client.get(f"{BASE}/personas/EMP-999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_full_week_schedule(client: TestClient) -> None:
    schedule = client.get(f"{BASE}/personas/EMP-001/schedule").json()
    assert schedule["week_id"] == "2026-W24"
    assert [d["day"] for d in schedule["days"]] == ["mon", "tue", "wed", "thu", "fri"]


def test_single_day(client: TestClient) -> None:
    day = client.get(f"{BASE}/personas/EMP-001/schedule/mon").json()
    assert day["day"] == "mon"
    assert day["blocks"][0]["category"] == "standup"
    # 30-minute resolution: every block carries a derived duration.
    assert all("duration_hours" in b for b in day["blocks"])


def test_single_day_invalid_weekday(client: TestClient) -> None:
    assert client.get(f"{BASE}/personas/EMP-001/schedule/sun").status_code == 422


def test_single_day_missing_persona(client: TestClient) -> None:
    assert client.get(f"{BASE}/personas/EMP-999/schedule/mon").status_code == 404


def test_signals_and_learning(client: TestClient) -> None:
    signals = client.get(f"{BASE}/personas/EMP-008/signals").json()
    assert set(signals) == {
        "employee_id",
        "meeting_hours_per_week",
        "focus_hours_per_week",
        "preferred_learning_slot",
        "collaboration_load",
    }
    learning = client.get(f"{BASE}/personas/EMP-008/learning").json()
    assert learning["exam_outcome"] in {"Pass", "Fail", "In Progress"}
    assert client.get(f"{BASE}/personas/EMP-999/signals").status_code == 404
    assert client.get(f"{BASE}/personas/EMP-999/learning").status_code == 404


def test_all_work_signals(client: TestClient) -> None:
    rows = client.get(f"{BASE}/work-signals").json()
    assert len(rows) == 11
    assert all("meeting_hours_per_week" in r for r in rows)


def test_team_roster(client: TestClient) -> None:
    team = client.get(f"{BASE}/teams/TEAM-A").json()
    assert team["name"] == "Atlas"
    assert len(team["member_employee_ids"]) == 11
    assert client.get(f"{BASE}/teams/TEAM-NOPE").status_code == 404


def test_team_capacity_is_aggregate_only(client: TestClient) -> None:
    capacity = client.get(f"{BASE}/teams/TEAM-A/capacity").json()
    # Manager surface: only aggregates, never per-learner identifiers or detail.
    assert set(capacity) == {
        "team_id",
        "team_name",
        "member_count",
        "avg_meeting_hours_per_week",
        "avg_focus_hours_per_week",
        "high_meeting_load_count",
        "readiness_distribution",
    }
    assert capacity["member_count"] == 11
    assert sum(capacity["readiness_distribution"].values()) == 11
    assert client.get(f"{BASE}/teams/TEAM-NOPE/capacity").status_code == 404


def test_all_routes_are_get_only(client: TestClient) -> None:
    # A read service must reject writes on its resources.
    for verb in ("post", "put", "patch", "delete"):
        response = getattr(client, verb)(f"{BASE}/personas/EMP-001")
        assert response.status_code == 405, f"{verb} should be 405"
