"""Dimension 1 — Accuracy & Relevance: grounding honesty battery.

Drives the live API and checks that the agent grounds an answer in catalog
sources only when the topic is genuinely covered (A1: no false grounding on a
single spurious keyword) and never sprawls one broad keyword across unrelated
courses (A5). The citation guard (A2) and number guard (A3/A4) are deterministic
functions verified by unit tests (``tests/test_guards*.py``) since they only
manifest when the LLM emits a malformed citation/figure.

Run:
    PYTHONPATH=. python -m agent_audit.dim1_accuracy           # offline lane
    PYTHONPATH=. python -m agent_audit.dim1_accuracy online
"""

from __future__ import annotations

import sys

from agent_audit.config import OFFLINE, ONLINE, Lane
from agent_audit.live_client import AthenaeumClient
from agent_audit.scorers import claimed_coverage, course_spread, grounded_with_sources
from agent_audit.seeds import BROAD_KEYWORD, GROUNDING_PROBES


def run(lane: Lane) -> dict:
    print(f"\n=== Dim 1 · Accuracy · lane={lane.name} ({lane.base_url}) ===")
    client = AthenaeumClient(lane.base_url)
    correct = 0
    for p in GROUNDING_PROBES:
        turn = client.ask(p.text)
        grounded = grounded_with_sources(turn) or claimed_coverage(turn)
        good = grounded if p.should_ground else not grounded
        correct += int(good)
        flag = "OK " if good else "BAD"
        print(
            f"  {flag} should_ground={p.should_ground!s:5} grounded={grounded!s:5} "
            f"route={turn.route} refs={turn.source_refs}"
        )
        if not good:
            print(f"      «{p.text[:55]}» -> {turn.visible_text[:70]!r}")

    spread_turn = client.ask(BROAD_KEYWORD.text)
    spread = course_spread(spread_turn)
    spread_ok = spread <= 1
    print(
        f"  {'OK ' if spread_ok else 'BAD'} broad-keyword '{BROAD_KEYWORD.text}': "
        f"{len(spread_turn.source_refs)} sources across {spread} course(s)"
    )

    total = len(GROUNDING_PROBES)
    print(f"  SUMMARY [{lane.name}]: grounding {correct}/{total} correct · spread-cap {spread_ok}")
    return {"lane": lane.name, "correct": correct, "total": total, "spread_ok": spread_ok}


def main(argv: list[str]) -> None:
    which = argv[1] if len(argv) > 1 else "offline"
    lanes = {"offline": [OFFLINE], "online": [ONLINE], "both": [OFFLINE, ONLINE]}[which]
    for lane in lanes:
        run(lane)


if __name__ == "__main__":
    main(sys.argv)
