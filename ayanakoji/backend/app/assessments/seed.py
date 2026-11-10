"""Startup seeding for the assessments DB — Azure Blob first, local JSON as fallback.

In a deployed environment the authored question banks live in Azure Blob (pushed by
``scripts/assessments_push.py``); that cloud copy is the source the running app pulls
from. Locally / in CI / offline there is no storage account, so we fall back to the
in-repo JSON banks. A blob failure (SDK missing, network, auth, bad bank) never blocks
boot: we log it and fall back to disk so the question bank is always populated from
*some* source. Endpoints already treat an empty bank as a valid empty result, so even a
total failure degrades gracefully rather than crashing the server.
"""

from __future__ import annotations

import logging

from app.assessments.engine import session_scope
from app.assessments.loader import seed_database

logger = logging.getLogger(__name__)


def seed_on_startup() -> dict[str, object]:
    """Seed ``assessments.db`` from the in-repo JSON question banks.

    Returns a summary dict with a ``source`` of ``"local"`` or ``"none"`` (seeding
    failed). Never raises — the app must boot regardless.
    """
    try:
        with session_scope() as session:
            summary = seed_database(session)
        logger.info("Seeded assessments.db from local banks: %s", summary)
        return {"source": "local", **summary}
    except Exception:  # noqa: BLE001 — never let seeding crash startup
        logger.exception("Local bank seed failed; assessments.db left as-is")
        return {"source": "none", "files": 0}
