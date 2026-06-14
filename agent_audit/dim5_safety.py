"""Dimension 5 — Reliability & Safety: the injection / jailbreak battery.

Attacks every gate-relevant seed (× converters) against a lane's live SSE API and
scores Attack-Success-Rate (ASR), block-rate, and the over-refusal anti-metric.

Run:
    PYTHONPATH=. python -m agent_audit.dim5_safety            # both lanes
    PYTHONPATH=. python -m agent_audit.dim5_safety offline    # one lane
"""

from __future__ import annotations

import sys

from agent_audit.config import OFFLINE, ONLINE, Lane
from agent_audit.converters import ALL_CONVERTERS
from agent_audit.live_client import AthenaeumClient
from agent_audit.scorers import attack_succeeded, over_refused, was_blocked
from agent_audit.seeds import (
    BENIGN_TRIGGERY,
    BLATANT_ATTACKS,
    EXFIL_ATTACKS,
    PARAPHRASED_ATTACKS,
    Probe,
)

# Converters to sweep over the paraphrased set. Offline is free, so sweep all;
# online is metered, so the caller can pass a smaller set.
_SWEEP = ("identity", "leetspeak", "confusable", "zero_width", "prefix_inject", "persona_wrap")


def _run_attacks(client: AthenaeumClient, probes: tuple[Probe, ...], label: str) -> dict:
    blocked = succeeded = 0
    survivors: list[str] = []
    for p in probes:
        turn = client.ask(p.text)
        if was_blocked(turn):
            blocked += 1
        if attack_succeeded(turn):
            succeeded += 1
            survivors.append(f"SUCCESS «{p.text[:60]}» — {turn.answer[:80]!r}")
        elif not was_blocked(turn):
            survivors.append(f"unblocked «{p.text[:60]}» ({p.note})")
    total = len(probes)
    print(f"  [{label}] {total} probes: blocked={blocked}, attack-success={succeeded}")
    for s in survivors:
        print(f"      - {s}")
    return {"label": label, "total": total, "blocked": blocked, "succeeded": succeeded}


def _run_converter_sweep(client: AthenaeumClient, converters: tuple[str, ...]) -> dict:
    """Paraphrased attacks × converters: does any obfuscation slip intent past?"""
    blocked = total = 0
    leaks: list[str] = []
    for cname in converters:
        conv = ALL_CONVERTERS[cname]
        cblocked = 0
        for p in PARAPHRASED_ATTACKS:
            turn = client.ask(conv(p.text))
            total += 1
            if was_blocked(turn):
                blocked += 1
                cblocked += 1
            elif attack_succeeded(turn):
                leaks.append(f"{cname}: «{p.text[:50]}»")
        print(f"    converter {cname:14s}: blocked {cblocked}/{len(PARAPHRASED_ATTACKS)}")
    print(f"  converter sweep: blocked {blocked}/{total}")
    for leak in leaks:
        print(f"      ! LEAK {leak}")
    return {"blocked": blocked, "total": total, "leaks": leaks}


def _run_overrefusal(client: AthenaeumClient) -> dict:
    refused = 0
    bad: list[str] = []
    for p in BENIGN_TRIGGERY:
        turn = client.ask(p.text)
        if over_refused(turn):
            refused += 1
            bad.append(f"OVER-REFUSED «{p.text[:60]}» ({p.note})")
    total = len(BENIGN_TRIGGERY)
    print(f"  over-refusal: {refused}/{total} benign messages wrongly blocked")
    for b in bad:
        print(f"      - {b}")
    return {"refused": refused, "total": total}


def run(lane: Lane, *, sweep: tuple[str, ...] = _SWEEP) -> dict:
    print(f"\n=== Dim 5 · Safety · lane={lane.name} ({lane.base_url}) ===")
    client = AthenaeumClient(lane.base_url)
    blatant = _run_attacks(client, BLATANT_ATTACKS, "blatant")
    paraphrased = _run_attacks(client, PARAPHRASED_ATTACKS, "paraphrased")
    exfil = _run_attacks(client, EXFIL_ATTACKS, "exfil")
    sweep_res = _run_converter_sweep(client, sweep)
    overref = _run_overrefusal(client)

    attack_total = blatant["total"] + paraphrased["total"] + exfil["total"]
    attack_blocked = blatant["blocked"] + paraphrased["blocked"] + exfil["blocked"]
    print(
        f"  SUMMARY [{lane.name}]: direct block-rate "
        f"{attack_blocked}/{attack_total} = {100 * attack_blocked / attack_total:.0f}%"
        f" · over-refusal {overref['refused']}/{overref['total']}"
    )
    return {
        "lane": lane.name,
        "blatant": blatant,
        "paraphrased": paraphrased,
        "exfil": exfil,
        "sweep": sweep_res,
        "overrefusal": overref,
    }


def main(argv: list[str]) -> None:
    which = argv[1] if len(argv) > 1 else "both"
    lanes = {"offline": [OFFLINE], "online": [ONLINE], "both": [OFFLINE, ONLINE]}[which]
    for lane in lanes:
        # Online is metered — sweep fewer converters there.
        sweep = ("identity", "confusable", "persona_wrap") if lane.online else _SWEEP
        run(lane, sweep=sweep)


if __name__ == "__main__":
    main(sys.argv)
