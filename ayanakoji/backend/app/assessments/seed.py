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
from app.assessments.loader import seed_database, seed_from_banks
from app.config import get_settings

logger = logging.getLogger(__name__)


def seed_on_startup() -> dict[str, object]:
    """Seed ``assessments.db``, preferring the Azure Blob copy of the banks.

    Returns a summary dict with a ``source`` of ``"azure_blob"``, ``"local"``, or
    ``"none"`` (both sources failed). Never raises — the app must boot regardless.
    """
    settings = get_settings()

    if settings.azure_storage_account:
        try:
            from app.assessments.azure_blob import pull_all_banks

            banks = pull_all_banks()
            with session_scope() as session:
                summary = seed_from_banks(session, banks)
            logger.info("Seeded assessments.db from Azure Blob: %s", summary)
            return {"source": "azure_blob", **summary}
        except Exception:  # noqa: BLE001 — any blob/SDK/validation failure → disk fallback
            logger.exception("Azure Blob seed failed; falling back to local banks")

    try:
        with session_scope() as session:
            summary = seed_database(session)
        logger.info("Seeded assessments.db from local banks: %s", summary)
        return {"source": "local", **summary}
    except Exception:  # noqa: BLE001 — never let seeding crash startup
        logger.exception("Local bank seed failed; assessments.db left as-is")
        return {"source": "none", "files": 0}
