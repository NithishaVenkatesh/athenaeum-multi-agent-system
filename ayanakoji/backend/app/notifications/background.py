"""Background cron loop that periodically runs the notifications/streak tick.

Started from the FastAPI lifespan and cancelled on shutdown. The tick is sync
(blocking SQLite), so it runs in a worker thread to keep the event loop free.
The loop sleeps *before* its first tick so importing/starting the app (and the
test client) never mutates the DB on startup — the read endpoint ticks lazily.
"""

from __future__ import annotations

import asyncio
import logging

from app.notifications.cron import run_tick

logger = logging.getLogger(__name__)


async def run_notification_loop(interval_seconds: int) -> None:
    """Tick every ``interval_seconds`` until cancelled. Never raises out of the loop."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            summary = await asyncio.to_thread(run_tick)
        except Exception:  # pragma: no cover - defensive: a bad tick must not kill the loop
            logger.exception("notification tick failed")
            continue
        if summary.notifications_created or summary.scoring_events_applied:
            logger.info(
                "notification tick: %d notifications, %d scoring events across %d personas",
                summary.notifications_created,
                summary.scoring_events_applied,
                summary.personas,
            )
