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
# A *strict* module-id shape (vertical-course-module, e.g. "cb-c01-m02"). Strict so a
# bare or parenthesized id in prose ("as covered in cb-c99-m99", "(cb-c99-m99)") is
# caught WITHOUT flagging ordinary hyphenated English ("real-world", "event-driven") —
# the citation guard is no longer bound to square brackets (A2).
_BARE_ID = re.compile(r"\b([a-z]{2}-c\d{1,2}-m\d{1,2})\b", re.IGNORECASE)
_WRAPPED_ID = re.compile(r"[\[(]?\b(?P<id>[a-z]{2}-c\d{1,2}-m\d{1,2})\b[\])]?", re.IGNORECASE)


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


# ── Role-aware quantity guard (A3) + spelled-out numbers (A4) ────────────────────
# The digit-membership check alone is role-blind: "all 12 modules across 12 weeks"
# passes against a 2-module/12-week plan because 12 appears *somewhere*. We also bind
# a stated quantity to its role ("<N> modules" must equal the module count) and read
# spelled-out figures ("twenty weeks") that "\d+" never saw.
_WORD_NUM = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100, "thousand": 1000,
    "couple": 2, "few": 3, "several": 4, "dozen": 12,
}  # fmt: skip
_NUM_WORD_ALT = "|".join(sorted(_WORD_NUM, key=len, reverse=True))
# A quantity: digits, or a run of number-words (e.g. "twenty five", "a couple hundred").
_QUANTITY = rf"\d+(?:\.\d+)?|(?:{_NUM_WORD_ALT})(?:[\s-]+(?:{_NUM_WORD_ALT}))*"
# A stated quantity bound to a plan role. Separator allows a hyphen ("12-week").
_ROLE_RE = re.compile(
    rf"(?P<qty>{_QUANTITY})[\s-]+(?P<role>modules?|weeks?|sessions?|hours?|hrs?|minutes?|mins?)\b",
    re.IGNORECASE,
)
_ROLE_KEYS = {
    "module": "modules", "week": "weeks", "session": "sessions",
    "hour": "hours", "hr": "hours", "minute": "minutes", "min": "minutes",
}  # fmt: skip


def _words_to_int(words: list[str]) -> int:
    """Compose a run of number-words into an int ('two hundred' → 200, 'twenty five' → 25)."""
    total = current = 0
    for word in words:
        value = _WORD_NUM.get(word)
        if value is None:
            continue
        if value == 100:
            current = (current or 1) * 100
        elif value == 1000:
            current = (current or 1) * 1000
            total += current
            current = 0
        else:
            current += value
    return total + current


def _qty_value(text: str) -> float:
    text = text.strip().lower()
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return float(text)
    return float(_words_to_int(re.split(r"[\s-]+", text)))


def _role_allowed(plan: StudyPlan) -> dict[str, set[str]]:
    minutes: set[str] = set()
    for m in plan.modules:
        minutes |= numbers_in(str(m.estimated_minutes))
    return {
        "modules": numbers_in(str(len(plan.modules))),
        "weeks": numbers_in(str(plan.weeks)),
        "sessions": numbers_in(str(len(plan.sessions))),
        "hours": numbers_in(str(plan.weekly_study_hours)) | numbers_in(str(plan.total_hours)),
        "minutes": minutes,
    }


def role_violations(narration: str, plan: StudyPlan) -> set[str]:
    """Quantities stated for a role that don't match the plan's value for that role."""
    allowed = _role_allowed(plan)
    bad: set[str] = set()
    for match in _ROLE_RE.finditer(narration):
        role = _ROLE_KEYS.get(match.group("role").lower().rstrip("s"))
        if role is None:
            continue
        value = _qty_value(match.group("qty"))
        norm = numbers_in(str(int(value)) if value.is_integer() else str(value))
        if norm and not norm <= allowed.get(role, set()):
            bad |= norm
    return bad


def plan_narration_is_grounded(narration: str, plan: StudyPlan) -> bool:
    """True iff every figure in the narration traces to the plan — value AND role.

    Two checks: (1) no quantity is bound to the wrong role ("12 modules" when the plan
    has 2, even though 12 is the week count), including spelled-out figures; and
    (2) no digit appears that the plan never computed at all.
    """
    if role_violations(narration, plan):
        return False
    return not ungrounded_numbers(narration, allowed_plan_numbers(plan))


# ── Citation guard (no fabricated module ids) ──────────────────────────────────


def cited_refs(text: str) -> list[str]:
    """Every module id an answer cites — bracketed, parenthesized, or bare — lowercased.

    Bracketed slugs are matched broadly (legacy behavior); strict module ids are also
    matched unbracketed so a phantom id in prose ("as covered in cb-c99-m99") is seen.
    """
    refs = [m.group(1).lower() for m in _CITATION.finditer(text)]
    refs += [m.group(1).lower() for m in _BARE_ID.finditer(text)]
    return refs


def unknown_citations(text: str, allowed_refs: Iterable[str]) -> set[str]:
    """Cited ids that aren't among the grounding sources (should be empty)."""
    allowed = {r.lower() for r in allowed_refs}
    return {ref for ref in cited_refs(text) if ref not in allowed}


def strip_unknown_citations(text: str, sources: Iterable[GroundingSource]) -> str:
    """Remove any id the answer invented that no source backs — bracketed OR bare.

    The grounded sources are the only legitimate citations; an LLM that fabricates a
    module id gets it scrubbed so the visible answer never cites a phantom, whether it
    wrote it as ``[cb-c99-m99]``, ``(cb-c99-m99)``, or bare ``cb-c99-m99`` in prose (A2).
    """
    allowed = {s.ref.lower() for s in sources}

    def _drop_bracketed(match: re.Match[str]) -> str:
        return match.group(0) if match.group(1).lower() in allowed else ""

    def _drop_wrapped(match: re.Match[str]) -> str:
        return match.group(0) if match.group("id").lower() in allowed else ""

    # Bracketed broad slugs first (legacy), then strict bare/parenthesized module ids.
    text = _CITATION.sub(_drop_bracketed, text)
    return _WRAPPED_ID.sub(_drop_wrapped, text)


# ── Streaming grounding enforcement (M5 live streaming + H5 honesty) ─────────────

# Only nag about missing citations once the answer has real substance, so a short
# "that isn't covered here" reply doesn't get a spurious disclaimer.
_MIN_CONTENT_FOR_DISCLAIMER = 60
_GROUNDING_DISCLAIMER = (
    " (Note: this answer goes beyond the cited course material above, "
    "double-check it against the linked modules.)"
)


def stream_grounded(tokens: Iterable[str], sources: Iterable[GroundingSource]) -> Iterator[str]:
    """Stream a tutor answer live while enforcing grounding (M5 + H5).

    Streams word by word (a word is held only until its trailing whitespace, never the
    whole answer), and for each word:
    - drops any invented module id before it reaches the client, whether the model wrote
      it bracketed ``[cb-c99-m99]``, parenthesized ``(cb-c99-m99)``, or bare in prose
      (``cb-c99-m99``) — the citation guard is no longer bound to square brackets (A2),
      and a real id (or non-citation bracket like ``[1]``) is passed through verbatim; and
    - if the answer produced real substance yet never cited a single approved source,
      appends one honesty disclaimer at the end (claims, not just ids).
    """
    allowed = {s.ref.lower() for s in sources}
    has_sources = bool(allowed)
    cited = False
    content_len = 0
    buf = ""  # current whitespace-delimited run

    def _scrub(run: str) -> str:
        """Keep allowed citations, drop invented module ids (bracketed/paren/bare)."""
        nonlocal cited, content_len
        if not run:
            return ""

        def _bracketed(match: re.Match[str]) -> str:
            nonlocal cited
            if match.group(1).lower() in allowed:
                cited = True
                return match.group(0)
            return ""  # invented bracketed slug, drop it

        def _wrapped(match: re.Match[str]) -> str:
            nonlocal cited
            if match.group("id").lower() in allowed:
                cited = True
                return match.group(0)
            return ""  # invented bare/parenthesized id, drop it

        cleaned = _WRAPPED_ID.sub(_wrapped, _CITATION.sub(_bracketed, run))
        content_len += len(cleaned)
        return cleaned

    for token in tokens:
        for ch in token:
            if ch.isspace():
                yield _scrub(buf) + ch
                buf = ""
            else:
                buf += ch
    if buf:
        yield _scrub(buf)
    if has_sources and not cited and content_len >= _MIN_CONTENT_FOR_DISCLAIMER:
        yield _GROUNDING_DISCLAIMER
