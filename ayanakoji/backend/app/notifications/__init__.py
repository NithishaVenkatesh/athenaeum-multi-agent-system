"""Learner notifications + streak/gamification (cron-driven).

A background tick derives notifications (module done, deadline soon/missed,
course complete) and the learner's streak score from the workspace's own state,
so every number is auditable and the tick is idempotent. The frontend polls the
read API and surfaces fresh notifications as live toasts.
"""
