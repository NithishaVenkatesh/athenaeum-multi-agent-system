"""Manager Insights surface — an additive, aggregate-only manager view.

This package is self-contained: it composes the existing Work IQ aggregate
repository (Source 1) and read-only course-activity queries (Source 2) into a
team-level insights view, plus a guarded manager chat that reuses the same
injection gate, prompt defenses, and grounding guards as the learner pipeline.

It NEVER exposes per-learner detail (only team aggregates) and does not modify
any existing module — the learner workspace is untouched.
"""
