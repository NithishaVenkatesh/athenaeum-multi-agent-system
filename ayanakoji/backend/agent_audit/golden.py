"""#27 — Golden-dataset regression runner.

A *golden dataset* is ground-truth I/O captured as JSONL (``datasets/<layer>.jsonl``),
one case per line:

    {"id", "layer", "input", "context"?: {...}, "expected": {...}, "category"?, "severity"?}

Each case is replayed against the real pipeline layer and the observed result is
compared to ``expected``. This is the cheap, durable regression gate to run on every
prompt/model change — it locks in the exact behaviors the hardening campaign established
(injection blocks, route choices, grounded-vs-not). It is purely additive: it only
*reads* the pipeline, never mutates ``app/`` or the database.

Usage:
    python -m agent_audit.golden                 # every dataset
    python -m agent_audit.golden --layer gate    # one layer
    python -m agent_audit.golden --json

``grounding`` is deterministic (no model call); ``gate`` and ``router`` hit the LIVE
model path, so run those when providers are reachable. Exit code is non-zero on any
mismatch, so this doubles as a CI gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

_DATASETS = Path(__file__).parent / "datasets"


@dataclass(frozen=True)
class GoldenResult:
    case_id: str
    layer: str
    passed: bool
    detail: str
    category: str = ""


# ── Per-layer probes: run the real layer, return (passed, observed-detail) ──────────


def _probe_gate(case: dict) -> tuple[bool, str]:
    from app.agent.gate import screen

    from agent_audit.harness import live_settings, shared_router

    ctx = case.get("context") or {}
    verdict, _ = screen(
        case["input"],
        router=shared_router(),
        history=ctx.get("history"),
        settings=live_settings(),
    )
    want = bool(case["expected"]["blocked"])
    return verdict.blocked == want, f"blocked={verdict.blocked} expected={want}"


def _probe_router(case: dict) -> tuple[bool, str]:
    from app.agent.grounding import get_grounding
    from app.agent.router_agent import route

    from agent_audit.harness import live_settings, shared_router

    ctx = case.get("context") or {}
    decision, _ = route(
        case["input"],
        router=shared_router(),
        grounding=get_grounding(),
        pending=ctx.get("pending"),
        history=ctx.get("history"),
        settings=live_settings(),
    )
    want = case["expected"]["route"]
    got = decision.route.value
    return got == want, f"route={got} expected={want}"


def _probe_grounding(case: dict) -> tuple[bool, str]:
    """Deterministic — no model call, so this layer runs free and offline-safe."""
    from app.agent.grounding import get_grounding

    ctx = case.get("context") or {}
    refs = [s.ref for s in get_grounding().search(case["input"], catalog_id=ctx.get("catalog_id"))]
    exp = case["expected"]
    if not exp.get("grounded", True):
        ok = len(refs) == 0
    else:
        ok = len(refs) > 0
        if ok and exp.get("course"):
            ok = all(r.startswith(exp["course"]) for r in refs)
        if ok and exp.get("not_course"):
            ok = all(not r.startswith(exp["not_course"]) for r in refs)
    return ok, f"refs={refs[:4]} expected={exp}"


_PROBES: dict[str, Callable[[dict], tuple[bool, str]]] = {
    "gate": _probe_gate,
    "router": _probe_router,
    "grounding": _probe_grounding,
}


def _load(layer: str) -> list[dict]:
    path = _DATASETS / f"{layer}.jsonl"
    if not path.exists():
        raise SystemExit(f"no golden dataset: {path}")
    cases: list[dict] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            cases.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{i} invalid JSON: {exc}") from exc
    return cases


def run_layer(layer: str) -> list[GoldenResult]:
    probe = _PROBES.get(layer)
    if probe is None:
        raise SystemExit(f"no probe for layer '{layer}' (known: {', '.join(sorted(_PROBES))})")
    results: list[GoldenResult] = []
    for case in _load(layer):
        try:
            passed, detail = probe(case)
        except Exception as exc:  # noqa: BLE001 — a probe crash is a failing case, surfaced
            passed, detail = False, f"probe error: {type(exc).__name__}: {exc}"
        results.append(
            GoldenResult(
                case_id=case["id"],
                layer=layer,
                passed=passed,
                detail=detail,
                category=case.get("category", ""),
            )
        )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Golden-dataset regression runner.")
    parser.add_argument("--layer", help="single layer (gate|router|grounding); default all")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    layers = [args.layer] if args.layer else sorted(_PROBES)
    all_results: list[GoldenResult] = []
    for layer in layers:
        all_results.extend(run_layer(layer))

    if args.json:
        print(
            json.dumps(
                [vars(r) for r in all_results],
                indent=2,
            )
        )
    else:
        for layer in layers:
            rs = [r for r in all_results if r.layer == layer]
            passed = sum(1 for r in rs if r.passed)
            status = "OK" if passed == len(rs) else "REGRESSION"
            print(f"=== {layer}: {passed}/{len(rs)} match → {status} ===")
            for r in rs:
                if not r.passed:
                    print(f"    [FAIL] {r.case_id} ({r.category}): {r.detail}")
        total = len(all_results)
        ok = sum(1 for r in all_results if r.passed)
        print(f"\n== golden: {ok}/{total} cases match ground truth ==")

    return 0 if all(r.passed for r in all_results) else 1


if __name__ == "__main__":
    sys.exit(main())
