"""Grounding guards — the rule-based layer that keeps answers honest.

The cert-prep winner earned Reliability with *guardrails + rule-based tests*,
not a research eval suite. These are pure, testable functions the pipeline (and
CI) use to assert that narration is grounded:

- **number-match**: an LLM narrating a study plan must only state numbers the
  deterministic plan actually computed — it never originates a figure.
- **no fabrication**: course/module ids in an answer must exist in the catalog.

Numbers are computed by the algorithm and *injected*; these guards detect any
that leaked in ungrounded, so a regression is caught rather than shipped.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator

from app.agent.contracts import GroundingSource, StudyPlan

_NUMBER = re.compile(r"\d+(?:\.\d+)?")
# A bracketed citation an answer makes, e.g. "[cb-c01-m02]". Module ids look like
# 2-4 lowercase-letter slug segments joined by hyphens; we only police that shape.
_CITATION = re.compile(r"\[([a-z]{2,}-[a-z0-9-]+)\]", re.IGNORECASE)


def numbers_in(text: str) -> set[str]:
    """All numeric tokens in a string, normalized (e.g. '3.0' and '3' both → '3')."""
    out: set[str] = set()
    for match in _NUMBER.findall(text):
        value = float(match)
        out.add(str(int(value)) if value.is_integer() else str(value))
    return out


def allowed_plan_numbers(plan: StudyPlan) -> set[str]:
    """Every number the plan legitimately exposes (hours, weeks, minutes, dates)."""
    allowed: set[str] = set()
    for value in (plan.weekly_study_hours, plan.total_hours, plan.weeks, len(plan.modules)):
        allowed |= numbers_in(str(value))
    for m in plan.modules:
        allowed |= numbers_in(str(m.estimated_minutes))
        allowed |= numbers_in(str(m.sequence))
        allowed |= numbers_in(m.complete_before)  # ISO date digits
        for b in m.scheduled:
            allowed |= numbers_in(f"{b.week} {b.start} {b.end} {b.minutes}")
    for s in plan.sessions:
        allowed |= numbers_in(f"{s.start} {s.end} {s.duration_minutes}")
    allowed |= numbers_in(plan.capacity_reason)
    allowed |= numbers_in(plan.start_date)
    return allowed


def ungrounded_numbers(narration: str, allowed: set[str]) -> set[str]:
    """Numbers in the narration that the plan never computed (should be empty)."""
    return numbers_in(narration) - allowed


def plan_narration_is_grounded(narration: str, plan: StudyPlan) -> bool:
    """True iff every number in the narration traces to the computed plan."""
    return not ungrounded_numbers(narration, allowed_plan_numbers(plan))


# ── Citation guard (no fabricated module ids) ──────────────────────────────────


def cited_refs(text: str) -> list[str]:
    """Every bracketed citation in an answer, lowercased (e.g. ['cb-c01-m02'])."""
    return [m.group(1).lower() for m in _CITATION.finditer(text)]


def unknown_citations(text: str, allowed_refs: Iterable[str]) -> set[str]:
    """Cited ids that aren't among the grounding sources (should be empty)."""
    allowed = {r.lower() for r in allowed_refs}
    return {ref for ref in cited_refs(text) if ref not in allowed}


def strip_unknown_citations(text: str, sources: Iterable[GroundingSource]) -> str:
    """Remove any bracketed id the answer invented that no source backs.

    The grounded sources are the only legitimate citations; an LLM that fabricates
    a [module-id] gets it scrubbed so the visible answer never cites a phantom.
    """
    allowed = {s.ref.lower() for s in sources}

    def _drop(match: re.Match[str]) -> str:
        return match.group(0) if match.group(1).lower() in allowed else ""

    return _CITATION.sub(_drop, text)


# ── Streaming grounding enforcement (M5 live streaming + H5 honesty) ─────────────

# Shape of a citation's inner id (matches _CITATION minus the brackets).
_CITATION_INNER = re.compile(r"[a-z]{2,}-[a-z0-9-]+", re.IGNORECASE)
# Longest a "[...]" run can get before we decide it is prose, not a citation.
_MAX_CITATION_LEN = 40
# Only nag about missing citations once the answer has real substance, so a short
# "that isn't covered here" reply doesn't get a spurious disclaimer.
_MIN_CONTENT_FOR_DISCLAIMER = 60
_GROUNDING_DISCLAIMER = (
    " (Note: this answer goes beyond the cited course material above, "
    "double-check it against the linked modules.)"
)


def stream_grounded(
    tokens: Iterable[str], sources: Iterable[GroundingSource]
) -> Iterator[str]:
    """Stream a tutor answer live while enforcing grounding (M5 + H5).

    Yields tokens as they arrive (no buffer-then-restream), but:
    - drops any invented ``[module-id]`` before it ever reaches the client,
      buffering only across an open ``[`` so the bracket can span model tokens
      (the citation guard, now streaming-safe); and
    - if the answer produced real substance yet never cited a single approved
      source, appends one honesty disclaimer at the end, so an ungrounded claim
      is flagged rather than passed off as sourced (claims, not just ids).
    """
    allowed = {s.ref.lower() for s in sources}
    has_sources = bool(allowed)
    pending = ""  # buffer while inside a candidate "[...]"
    content_len = 0
    cited = False

    def _resolve(bracket: str) -> str:
        """Decide a completed/abandoned bracket buffer: keep, drop, or pass through."""
        nonlocal cited
        inner = bracket[1:-1] if bracket.endswith("]") else bracket[1:]
        if bracket.endswith("]") and _CITATION_INNER.fullmatch(inner):
            if inner.lower() in allowed:
                cited = True
                return bracket  # a real citation, keep it verbatim
            return ""  # invented id, drop it
        return bracket  # not citation-shaped, it was just prose

    for token in tokens:
        out: list[str] = []
        for ch in token:
            if pending:
                if ch == "[":  # a new bracket opened before the last closed → prose
                    out.append(_resolve(pending))
                    pending = "["
                else:
                    pending += ch
                    if ch == "]" or len(pending) > _MAX_CITATION_LEN:
                        out.append(_resolve(pending))
                        pending = ""
            elif ch == "[":
                pending = "["
            else:
                out.append(ch)
        if out:
            chunk = "".join(out)
            content_len += sum(len(p) for p in out if not _CITATION.fullmatch(p))
            yield chunk
    if pending:  # unterminated "[..." at end of stream
        yield _resolve(pending)
    if has_sources and not cited and content_len >= _MIN_CONTENT_FOR_DISCLAIMER:
        yield _GROUNDING_DISCLAIMER
