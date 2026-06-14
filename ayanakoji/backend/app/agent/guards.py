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
import unicodedata
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
# Any digit count after c/m: real ids are cNN-mNN, but a fabricated 3+ digit suffix
# (cb-c01-m001, cb-c01-m100) must still be recognized and scrubbed (red-team A2 gap).
_BARE_ID = re.compile(r"\b([a-z]{2}-c\d+-m\d+)\b", re.IGNORECASE)
_WRAPPED_ID = re.compile(r"[\[(]?\b(?P<id>[a-z]{2}-c\d+-m\d+)\b[\])]?", re.IGNORECASE)

# ── Obfuscation-robust id recognition (normalize → membership, NOT more regex) ───
# The earlier guards equated *recognition* with the ASCII byte-shape, so an id-shaped
# token was invisible to the guard the moment it was obfuscated — a Cyrillic prefix
# (``сb-c99-m99``), superscript digits (``cb-c⁹⁹-m⁹⁹``), or spaces around the hyphens
# (``cb - c99 - m99``) all sailed through unstripped because the regex never tokenized
# them as ids at all. The homoglyph/script space is infinite, so the fix is algorithmic:
#
#   1. ONE deliberately permissive *shape* scanner finds candidate id tokens — any two
#      leading letters (incl. homoglyphs), the ``c``/``m`` segment markers, digit-ish
#      glyphs (incl. superscripts/fullwidth), and optional whitespace around the hyphens;
#   2. each candidate's visible text is NORMALIZED (NFKC folds superscript/fullwidth
#      digits → ascii; a minimal confusables fold maps look-alike letters → ascii; intra-
#      token whitespace is collapsed), THEN the *normalized* form is checked against the
#      allowed source ids (set membership). A normalized id in the allowed set is KEPT;
#      one that is not is STRIPPED — and the ORIGINAL (obfuscated) span is what we remove.
#
# This keeps recognition decoupled from the exact glyphs while preserving the existing
# semantics: real source ids pass verbatim, non-citation brackets like ``[1]`` are
# untouched (they never match the c/m id shape), and phantom ids are scrubbed in ascii,
# homoglyph, superscript, OR spaced form. We do NOT import gate_heuristic (avoid coupling).

# Minimal Cyrillic/Greek look-alike fold — only the glyphs that can appear inside a
# module-id token (the letters of "cb-cNN-mNN" plus common vertical prefixes). Mirrors
# the idea of gate_heuristic._CONFUSABLES without importing it.
_ID_CONFUSABLES = {
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "ѕ": "s",
    "і": "i", "ј": "j", "к": "k", "м": "m", "н": "h", "т": "t", "в": "b", "ԁ": "d",
    "ɡ": "g", "ν": "v", "α": "a", "ε": "e", "ο": "o", "ρ": "p", "ⅿ": "m", "ｃ": "c",
}  # fmt: skip
# Permissive id-shape scanner. ``[^\W\d_]`` is "any unicode letter" (so a homoglyph
# prefix matches); ``c``/``m`` markers are matched after folding by re-deriving them
# from the candidate; ``[^\s\-]`` for the segment bodies admits superscript/fullwidth
# digits (which are not ``\d``); optional ``\s*`` straddles the hyphens for spaced ids.
_ID_SHAPE = re.compile(
    r"[^\W\d_]{2}\s*-\s*[^\W\d_]\s*[^\s\-\]\)]{1,4}\s*-\s*[^\W\d_]\s*[^\s\-\]\)]{1,4}",
    re.UNICODE,
)


def _fold_id(token: str) -> str:
    """Normalize an obfuscated id-shaped token to its canonical ascii compact form.

    NFKC folds superscript/fullwidth digits and many compatibility glyphs to ascii;
    the confusables map folds look-alike letters; whitespace is dropped so a spaced id
    collapses to ``cb-c99-m99``. The result is what we check for set-membership.
    """
    folded = unicodedata.normalize("NFKC", token)
    folded = "".join(_ID_CONFUSABLES.get(c, c) for c in folded)
    folded = re.sub(r"\s+", "", folded)
    return folded.lower()


def _looks_like_id(folded: str) -> bool:
    """True iff a *folded* token has the canonical module-id shape (xx-cNN-mNN)."""
    return bool(_BARE_ID.fullmatch(folded))


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
    Obfuscated id-shaped tokens (homoglyph prefix, superscript digits, spaced hyphens)
    are recognized too — each candidate is normalized (NFKC + confusables + whitespace
    fold) and reported in its canonical compact form so the oracle sees a real id.
    """
    refs = [m.group(1).lower() for m in _CITATION.finditer(text)]
    refs += [m.group(1).lower() for m in _BARE_ID.finditer(text)]
    for m in _ID_SHAPE.finditer(text):
        folded = _fold_id(m.group(0))
        if _looks_like_id(folded):
            refs.append(folded)
    return refs


def unknown_citations(text: str, allowed_refs: Iterable[str]) -> set[str]:
    """Cited ids that aren't among the grounding sources (should be empty)."""
    allowed = {r.lower() for r in allowed_refs}
    return {ref for ref in cited_refs(text) if ref not in allowed}


def strip_unknown_citations(text: str, sources: Iterable[GroundingSource]) -> str:
    """Remove any id the answer invented that no source backs — bracketed OR bare.

    The grounded sources are the only legitimate citations; an LLM that fabricates a
    module id gets it scrubbed so the visible answer never cites a phantom, whether it
    wrote it as ``[cb-c99-m99]``, ``(cb-c99-m99)``, bare ``cb-c99-m99`` in prose (A2),
    or *obfuscated* — a homoglyph prefix (``сb-c99-m99``), superscript digits
    (``cb-c⁹⁹-m⁹⁹``), or spaces around the hyphens (``cb - c99 - m99``). Recognition is
    decoupled from the byte-shape: an id-shaped token is normalized (NFKC + confusables +
    whitespace fold) and the *normalized* form checked against the allowed source set; a
    member is kept verbatim, a non-member has its ORIGINAL (obfuscated) span removed.
    """
    allowed = {s.ref.lower() for s in sources}

    def _drop_bracketed(match: re.Match[str]) -> str:
        return match.group(0) if match.group(1).lower() in allowed else ""

    def _drop_wrapped(match: re.Match[str]) -> str:
        return match.group(0) if match.group("id").lower() in allowed else ""

    def _drop_obfuscated(match: re.Match[str]) -> str:
        folded = _fold_id(match.group(0))
        if not _looks_like_id(folded):
            return match.group(0)  # not actually an id shape once folded — leave alone
        return match.group(0) if folded in allowed else ""

    # Bracketed broad slugs first (legacy), then strict bare/parenthesized ascii ids,
    # then the permissive normalize-then-membership pass for obfuscated id-shaped tokens.
    text = _CITATION.sub(_drop_bracketed, text)
    text = _WRAPPED_ID.sub(_drop_wrapped, text)
    return _ID_SHAPE.sub(_drop_obfuscated, text)


# ── Streaming grounding enforcement (M5 live streaming + H5 honesty) ─────────────

# Only nag about missing citations once the answer has real substance, so a short
# "that isn't covered here" reply doesn't get a spurious disclaimer.
_MIN_CONTENT_FOR_DISCLAIMER = 60
_GROUNDING_DISCLAIMER = (
    " (Note: this answer goes beyond the cited course material above, "
    "double-check it against the linked modules.)"
)


# A *spaced* obfuscated id straddles several whitespace runs ("cb - c99 - m99"), so the
# stream scrubber cannot decide a run in isolation — it must hold a run back while that
# run could still be the start/middle of an id shape. This matches a token that is a
# possible PREFIX of a (possibly spaced, possibly obfuscated) id, so we keep buffering
# until we know the boundary is safe to flush.
_ID_PREFIX = re.compile(
    r"^[^\W\d_]{2}(\s*-\s*(?:[^\W\d_]\s*[^\s\-\]\)]{0,4}(\s*-\s*[^\W\d_]?\s*[^\s\-\]\)]{0,4})?)?)?$",
    re.UNICODE,
)


def stream_grounded(tokens: Iterable[str], sources: Iterable[GroundingSource]) -> Iterator[str]:
    """Stream a tutor answer live while enforcing grounding (M5 + H5).

    Streams in small flushes (a run is held only until it is provably not part of an
    in-progress id, never the whole answer), and:
    - drops any invented module id before it reaches the client, whether the model wrote
      it bracketed ``[cb-c99-m99]``, parenthesized ``(cb-c99-m99)``, bare in prose
      (``cb-c99-m99``), or *obfuscated* — homoglyph prefix (``сb-c99-m99``), superscript
      digits (``cb-c⁹⁹-m⁹⁹``), or spaced hyphens (``cb - c99 - m99``); recognition is
      normalize-then-membership, not the byte-shape (A2), and a real id (or non-citation
      bracket like ``[1]``) is passed through verbatim; and
    - if the answer produced real substance yet never cited a single approved source,
      appends one honesty disclaimer at the end (claims, not just ids).
    """
    allowed = {s.ref.lower() for s in sources}
    has_sources = bool(allowed)
    cited = False
    content_len = 0
    # ``segment`` accumulates runs+separators that might together form a spaced id; it is
    # scrubbed and flushed as soon as the trailing run can no longer extend an id shape.
    segment = ""

    def _scrub(run: str) -> str:
        """Keep allowed citations, drop invented module ids (ascii/obfuscated)."""
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

        def _obfuscated(match: re.Match[str]) -> str:
            nonlocal cited
            folded = _fold_id(match.group(0))
            if not _looks_like_id(folded):
                return match.group(0)  # not an id once folded — leave verbatim
            if folded in allowed:
                cited = True
                return match.group(0)
            return ""  # invented id (any glyph/spacing), drop it

        cleaned = _ID_SHAPE.sub(
            _obfuscated, _WRAPPED_ID.sub(_wrapped, _CITATION.sub(_bracketed, run))
        )
        content_len += len(cleaned)
        return cleaned

    def _last_run(seg: str) -> str:
        """The trailing whitespace-delimited run of ``seg`` (may be empty)."""
        return re.split(r"\s", seg)[-1]

    for token in tokens:
        for ch in token:
            segment += ch
            if not ch.isspace():
                continue
            # A separator arrived. If the segment so far still *could* be an id in
            # progress (its compact tail is a valid id-prefix), keep buffering; else the
            # segment is settled — scrub and flush it whole.
            tail = re.sub(r"\s+", "", segment)
            if tail and _ID_PREFIX.match(tail) and not _looks_like_id(tail.lower()):
                continue
            yield _scrub(segment)
            segment = ""
    if segment:
        yield _scrub(segment)
    if has_sources and not cited and content_len >= _MIN_CONTENT_FOR_DISCLAIMER:
        yield _GROUNDING_DISCLAIMER
