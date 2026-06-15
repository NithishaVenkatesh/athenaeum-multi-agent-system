"""Dedicated Azure AI evaluation layer — NLI-style judges over a grounded answer.

This is the cloud adapter behind ``answer.verify_grounding``. Where the deterministic
floor (``guards.lexical_groundedness``) only catches a citation lifted onto a topic-
disjoint claim, these are LLM-as-judge evaluators that reason about *entailment*:

- **Groundedness** — is every claim in the answer supported by the cited context? This is
  the decision-driver: below the configured score the answer is treated as ungrounded and
  gets the honesty disclaimer even though it cites a real module id.
- **Relevance** — does the answer actually address the question?
- **Retrieval** — was the retrieved context relevant/well-ranked for the query?
- **Groundedness Pro** (best-effort) — the Content-Safety-backed groundedness check, run
  when an Azure AI project is configured; skipped cleanly otherwise.

The evaluators run in parallel (each is one Azure OpenAI call) to keep the post-answer
latency near a single call. SDK imports are lazy so the offline lane imports this module
without ``azure-ai-evaluation`` installed; any failure raises so the caller degrades to
the deterministic floor — verification never blocks the answer.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import cast

from app.agent.contracts import GroundingSource
from app.agent.guards import GroundingVerdict
from app.config import Settings

# Evaluators score on a 1..5 scale; we normalize to 0..1 for the verdict's headline score.
_EVAL_MAX = 5.0


def _context_block(sources: Iterable[GroundingSource]) -> str:
    """The cited grounding context the evaluators judge the answer against."""
    return "\n\n".join(f"[{s.ref}] {s.title}: {s.snippet}" for s in sources)


def _extract_score(result: Mapping[str, object], name: str) -> float | None:
    """Pull a clean 1..5 score from an evaluator result, tolerating the retrieval ``nan``.

    The evaluators expose ``{name}`` as the score; the retrieval evaluator can return
    ``nan`` there while the real score sits in ``{name}_properties.score`` — fall back to it.
    """

    def _num(value: object) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int | float):
            f = float(value)
            return None if math.isnan(f) else f
        return None

    primary = _num(result.get(name))
    if primary is not None:
        return primary
    props = result.get(f"{name}_properties")
    if isinstance(props, dict):
        return _num(props.get("score"))
    return None


def azure_grounding(
    query: str,
    answer: str,
    sources: list[GroundingSource],
    settings: Settings,
) -> GroundingVerdict:
    """Score a grounded answer with the Azure AI evaluation judges → a GroundingVerdict.

    Raises if the groundedness judge yields no usable score, so the caller falls back to
    the deterministic lexical floor.
    """
    from azure.ai.evaluation import (
        AzureOpenAIModelConfiguration,
        GroundednessEvaluator,
        RelevanceEvaluator,
        RetrievalEvaluator,
    )

    foundry = settings.require_foundry()
    model_config = AzureOpenAIModelConfiguration(
        azure_endpoint=foundry.openai_endpoint,
        api_key=foundry.openai_api_key,
        azure_deployment=foundry.model_workhorse,
        api_version=foundry.openai_api_version,
    )
    context = _context_block(sources)

    def _groundedness() -> Mapping[str, object]:
        result = GroundednessEvaluator(model_config)(query=query, response=answer, context=context)
        return cast("Mapping[str, object]", result)

    def _relevance() -> Mapping[str, object]:
        result = RelevanceEvaluator(model_config)(query=query, response=answer)
        return cast("Mapping[str, object]", result)

    def _retrieval() -> Mapping[str, object]:
        result = RetrievalEvaluator(model_config)(query=query, context=context)
        return cast("Mapping[str, object]", result)

    # Independent judges → run concurrently so the post-answer wait is ~one call, not four.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            "groundedness": pool.submit(_groundedness),
            "relevance": pool.submit(_relevance),
            "retrieval": pool.submit(_retrieval),
        }
        results: dict[str, Mapping[str, object]] = {}
        for name, future in futures.items():
            try:
                results[name] = future.result(timeout=settings.evaluation_timeout_seconds)
            except Exception:  # noqa: BLE001 — a single judge failing must not sink the rest
                results[name] = {}

    metrics: list[tuple[str, float]] = []
    reasons: list[str] = []
    for name in ("groundedness", "relevance", "retrieval"):
        score = _extract_score(results[name], name)
        if score is not None:
            metrics.append((name, round(score, 1)))
        reason = results[name].get(f"{name}_reason")
        if isinstance(reason, str) and reason.strip():
            reasons.append(f"{name}: {reason.strip()[:160]}")

    pro_score = _groundedness_pro(query, answer, context, settings)
    if pro_score is not None:
        metrics.append(("groundedness_pro", round(pro_score, 1)))

    groundedness_score = _extract_score(results["groundedness"], "groundedness")
    if groundedness_score is None:
        raise RuntimeError("Azure groundedness evaluation produced no score")

    # The verdict gates on EVERY judge that produced a score. Groundedness is mandatory
    # (it raised above if absent). Relevance / retrieval / pro gate ONLY when their judge
    # returned a number: a judge that errored (result {} → _extract_score None) must not
    # block the answer — fail-open for an absent judge, fail-closed only on a real low
    # score. (groundedness_pro is read on the same 1..5 rubric; if that scale is ever
    # wrong it can only wrongly *tighten* one already-OK-on-groundedness answer, and it's
    # usually absent anyway, so we keep it in the same all-judges gate.)
    relevance_score = _extract_score(results["relevance"], "relevance")
    retrieval_score = _extract_score(results["retrieval"], "retrieval")

    failures: list[str] = []
    if groundedness_score < settings.groundedness_min_score:
        failures.append(
            f"groundedness {groundedness_score:g} < {settings.groundedness_min_score:g}"
        )
    if relevance_score is not None and relevance_score < settings.relevance_min_score:
        failures.append(f"relevance {relevance_score:g} < {settings.relevance_min_score:g}")
    if retrieval_score is not None and retrieval_score < settings.retrieval_min_score:
        failures.append(f"retrieval {retrieval_score:g} < {settings.retrieval_min_score:g}")
    if pro_score is not None and pro_score < settings.groundedness_pro_min_score:
        failures.append(
            f"groundedness_pro {pro_score:g} < {settings.groundedness_pro_min_score:g}"
        )

    grounded = not failures
    if grounded:
        reason = " | ".join(reasons) or "claims supported by the cited modules"
    else:
        # Name which judge(s) failed so the trace is honest, then append the judge prose.
        reason = " | ".join([*failures, *reasons]) or (
            "a claim is not supported by the cited modules"
        )
    return GroundingVerdict(
        grounded=grounded,
        reason=reason[:400],
        provider="Azure AI evaluation",
        score=round(groundedness_score / _EVAL_MAX, 2),
        metrics=tuple(metrics),
    )


def _groundedness_pro(query: str, answer: str, context: str, settings: Settings) -> float | None:
    """Best-effort Content-Safety-backed groundedness; None when its resource is absent."""
    project = settings.foundry_project_endpoint
    if not project:
        return None
    try:
        from azure.ai.evaluation import GroundednessProEvaluator
        from azure.identity import DefaultAzureCredential

        result = GroundednessProEvaluator(
            azure_ai_project=project, credential=DefaultAzureCredential()
        )(query=query, response=answer, context=context)
        return _extract_score(result, "groundedness_pro")
    except Exception:  # noqa: BLE001 — no Content Safety project → just skip this metric
        return None
