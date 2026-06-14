"""Harness configuration: the two live lanes, personas, and catalog ids.

Ports are the clean-room red-team instances stood up for this campaign, NOT the
developer's dev servers (which race on :8000). Each red-team lane uses a throwaway
SQLite DB so attack traffic never pollutes the real workspace.
"""

from __future__ import annotations

from dataclasses import dataclass

# Red-team lanes (uvicorn instances started for the audit).
OFFLINE_BASE = "http://localhost:8020"  # OFFLINE_LLM=true — degraded / all-providers-down
ONLINE_BASE = "http://localhost:8021"  # real Azure + Groq — production safety + answer layer

# Default per-request timeout (online answers + classifier round-trips are slow).
DEFAULT_TIMEOUT = 90.0

# Personas (from app/data/work_iq.json). One per vertical so grounding scope varies.
PERSONAS = {
    "cloud-backend": "EMP-001",  # Vega, Senior Backend Engineer
    "devops-platform": "EMP-003",  # Rigel
    "data-engineering": "EMP-005",  # Lyra
    "ai-ml": "EMP-007",  # Orion
    "architecture-security": "EMP-009",  # Atlas
    "management": "EMP-011",  # Polaris
}
DEFAULT_PERSONA = "EMP-001"

# A few catalog course ids used to set up locked-chat / in-course scenarios.
COURSE_COMPUTE = "cb-c01"  # Azure Compute & Serverless Foundations (Functions, App Service)
COURSE_SECURITY = "cb-c03"  # Securing & Integrating Cloud Apps (Secrets, keys, identities)
COURSE_DATA = "de-c01"  # Data Storage & Lakehouse Design


@dataclass(frozen=True)
class Lane:
    """A target lane for the harness."""

    name: str
    base_url: str
    online: bool


OFFLINE = Lane(name="offline", base_url=OFFLINE_BASE, online=False)
ONLINE = Lane(name="online", base_url=ONLINE_BASE, online=True)
