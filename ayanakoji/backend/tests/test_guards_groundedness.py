"""Claim-support (groundedness) guard tests — a citation must back its claim.

The deterministic lexical floor catches a real module id lifted onto a topic-disjoint
claim (the case the id-existence guard misses). It cannot judge an on-topic-but-false
claim; that is the live NLI evaluator's job (tested separately).
"""

from __future__ import annotations

from app.agent.contracts import GroundingSource
from app.agent.guards import groundedness_disclaimer, lexical_groundedness

_FUNCTIONS = GroundingSource(
    ref="cb-c01-m02",
    title="Event-driven code with Azure Functions",
    snippet=(
        "Build serverless functions with triggers and input/output bindings. Objectives: "
        "Create and configure an Azure Functions app; Implement triggers using timers and "
        "webhooks; Wire input and output bindings to reduce boilerplate."
    ),
    kind="course",
)


def test_supported_citation_is_grounded() -> None:
    answer = "Azure Functions use triggers to start and bindings to connect services [cb-c01-m02]."
    verdict = lexical_groundedness(answer, [_FUNCTIONS])
    assert verdict.grounded is True
    assert verdict.score == 1.0
    assert groundedness_disclaimer(verdict) is None
    assert verdict.metrics  # the claim_support score is reported


def test_real_id_on_topic_disjoint_claim_is_flagged() -> None:
    # A real, existing module id attached to a claim about a different topic: the
    # id-existence guard would pass it; the claim-support floor flags it.
    answer = "Cosmos DB partition keys shard throughput across physical partitions [cb-c01-m02]."
    verdict = lexical_groundedness(answer, [_FUNCTIONS])
    assert verdict.grounded is False
    assert "cb-c01-m02" in verdict.unsupported
    assert groundedness_disclaimer(verdict) is not None


def test_no_citation_is_grounded_and_silent() -> None:
    # No approved citation to verify — the streaming guard's no-citation disclaimer
    # handles that case, so this returns grounded with nothing to report.
    verdict = lexical_groundedness("A general explanation with no citation.", [_FUNCTIONS])
    assert verdict.grounded is True
    assert verdict.metrics == ()
    assert groundedness_disclaimer(verdict) is None


def test_no_sources_is_grounded() -> None:
    verdict = lexical_groundedness("Anything at all.", [])
    assert verdict.grounded is True


def test_single_shared_term_is_no_longer_grounded() -> None:
    """The lexical floor now requires >=2 salient overlapping terms, not 1.

    The source's only salient terms (after stopword/short-word filtering) here are
    ``triggers`` and ``handlers``. A sentence that shares exactly ONE of them is now
    flagged (a lone incidental keyword is not support); sharing BOTH is grounded.
    """
    src = GroundingSource(ref="cb-c01-m02", title="Triggers", snippet="handlers", kind="course")
    one_term = "The triggers diagram explains everything about distributed consensus [cb-c01-m02]."
    two_terms = "The triggers and handlers are described here [cb-c01-m02]."

    flagged = lexical_groundedness(one_term, [src])
    assert flagged.grounded is False
    assert "cb-c01-m02" in flagged.unsupported

    ok = lexical_groundedness(two_terms, [src])
    assert ok.grounded is True


def test_partial_support_flags_only_the_unsupported_citation() -> None:
    answer = (
        "Azure Functions run on triggers and bindings [cb-c01-m02]. "
        "Separately, slot swaps give zero-downtime deploys [cb-c01-m99]."
    )
    other = GroundingSource(
        ref="cb-c01-m99", title="Unrelated", snippet="quantum cryptography lattices", kind="course"
    )
    verdict = lexical_groundedness(answer, [_FUNCTIONS, other])
    assert verdict.grounded is False
    assert verdict.unsupported == ("cb-c01-m99",)
    assert 0.0 < (verdict.score or 0.0) < 1.0
