"""One-command scorecard: run the dimension batteries and print a single table.

This is a thin aggregator over the existing runners — it does NOT change them.
It calls :func:`agent_audit.dim1_accuracy.run` and :func:`agent_audit.dim5_safety.run`
and reduces their returned dicts into the headline metrics a reviewer wants:

    groundedness / relevance (Dim 1)   — grounding-honesty pass count + spread cap
    injection block-rate     (Dim 5)   — blatant / paraphrased / exfil block-rate
    over-refusal anti-metric (Dim 5)   — benign learner messages wrongly blocked
    attack-success (ASR)     (Dim 5)   — leaks or attacker-persona compliance

Like every battery here it drives the **live** lanes, so it makes network calls
and (online) spends real Azure/Groq tokens. It is therefore opt-in: nothing
imports it, and it only runs when invoked directly.

Run:
    PYTHONPATH=. python -m agent_audit.scorecard            # offline lane (free)
    PYTHONPATH=. python -m agent_audit.scorecard online     # online lane (metered)
    PYTHONPATH=. python -m agent_audit.scorecard both
"""

from __future__ import annotations

import sys

from agent_audit import dim1_accuracy, dim5_safety
from agent_audit.config import OFFLINE, ONLINE, Lane


def _pct(num: int, denom: int) -> str:
    return f"{100 * num / denom:.0f}%" if denom else "n/a"


def _row(label: str, value: str, detail: str = "") -> str:
    return f"  {label:<26} {value:>10}   {detail}"


def summarize(lane: Lane) -> dict:
    """Run both dimensions against one lane and return the headline numbers."""
    # Online is metered: mirror dim5_safety.main's smaller converter sweep there.
    sweep = ("identity", "confusable", "persona_wrap") if lane.online else dim5_safety._SWEEP

    d1 = dim1_accuracy.run(lane)
    d5 = dim5_safety.run(lane, sweep=sweep)

    attack_total = d5["blatant"]["total"] + d5["paraphrased"]["total"] + d5["exfil"]["total"]
    attack_blocked = d5["blatant"]["blocked"] + d5["paraphrased"]["blocked"] + d5["exfil"]["blocked"]
    attack_succeeded = (
        d5["blatant"]["succeeded"] + d5["paraphrased"]["succeeded"] + d5["exfil"]["succeeded"]
    )

    return {
        "lane": lane.name,
        "grounding_correct": d1["correct"],
        "grounding_total": d1["total"],
        "spread_ok": d1["spread_ok"],
        "blatant": d5["blatant"],
        "paraphrased": d5["paraphrased"],
        "exfil": d5["exfil"],
        "sweep": d5["sweep"],
        "overrefusal": d5["overrefusal"],
        "attack_total": attack_total,
        "attack_blocked": attack_blocked,
        "attack_succeeded": attack_succeeded,
    }


def print_table(rows: list[dict]) -> None:
    print("\n" + "=" * 64)
    print("  AGENT-AUDIT SCORECARD  (harness-measured, this run)")
    print("=" * 64)
    for r in rows:
        b, p, e = r["blatant"], r["paraphrased"], r["exfil"]
        sw, orf = r["sweep"], r["overrefusal"]
        print(f"\n  lane = {r['lane']}")
        print(
            _row(
                "grounding-honesty",
                _pct(r["grounding_correct"], r["grounding_total"]),
                f"{r['grounding_correct']}/{r['grounding_total']} probes correct",
            )
        )
        print(_row("cross-course spread cap", "PASS" if r["spread_ok"] else "FAIL", "broad keyword <= 1 course"))
        print(
            _row(
                "injection block-rate",
                _pct(r["attack_blocked"], r["attack_total"]),
                f"{r['attack_blocked']}/{r['attack_total']} direct attacks blocked",
            )
        )
        print(_row("  · blatant", _pct(b["blocked"], b["total"]), f"{b['blocked']}/{b['total']}"))
        print(_row("  · paraphrased", _pct(p["blocked"], p["total"]), f"{p['blocked']}/{p['total']}"))
        print(_row("  · exfil", _pct(e["blocked"], e["total"]), f"{e['blocked']}/{e['total']}"))
        print(
            _row(
                "converter sweep",
                _pct(sw["blocked"], sw["total"]),
                f"{sw['blocked']}/{sw['total']} blocked, {len(sw['leaks'])} leaks",
            )
        )
        print(
            _row(
                "attack-success (ASR)",
                str(r["attack_succeeded"]),
                "leak or attacker-persona compliance (lower = better)",
            )
        )
        print(
            _row(
                "over-refusal (anti-metric)",
                f"{orf['refused']}/{orf['total']}",
                "benign learner messages wrongly blocked (lower = better)",
            )
        )
    print("\n" + "=" * 64)


def main(argv: list[str]) -> None:
    which = argv[1] if len(argv) > 1 else "offline"
    lanes = {"offline": [OFFLINE], "online": [ONLINE], "both": [OFFLINE, ONLINE]}[which]
    rows = [summarize(lane) for lane in lanes]
    print_table(rows)


if __name__ == "__main__":
    main(sys.argv)
