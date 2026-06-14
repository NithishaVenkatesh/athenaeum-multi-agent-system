"""CLI runner for the live red-team batteries.

    python -m agent_audit.run --layer gate --rounds 2
    python -m agent_audit.run --all --rounds 2 --json

Each battery module is ``agent_audit.attacks_<layer>`` exposing ``LAYER`` and
``run() -> list[CaseResult]``. Exit code is non-zero if any selected layer does not
hold, so this doubles as a CI gate.
"""

from __future__ import annotations

import argparse
import importlib
import json
import pkgutil
import sys
from collections.abc import Iterable

import agent_audit
from agent_audit.harness import LayerReport, format_report, report_to_dict, run_battery


def _discover_layers() -> list[str]:
    """All ``attacks_<layer>`` modules present in the package."""
    layers: list[str] = []
    for mod in pkgutil.iter_modules(agent_audit.__path__):
        if mod.name.startswith("attacks_"):
            layers.append(mod.name[len("attacks_") :])
    return sorted(layers)


def _run_one(layer: str, rounds: int) -> LayerReport:
    module = importlib.import_module(f"agent_audit.attacks_{layer}")
    if not hasattr(module, "run"):
        raise SystemExit(f"battery agent_audit.attacks_{layer} has no run()")
    return run_battery(module.run, layer=getattr(module, "LAYER", layer), rounds=rounds)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live red-team audit of the agent pipeline.")
    parser.add_argument("--layer", help="single layer to audit (e.g. gate, router)")
    parser.add_argument("--all", action="store_true", help="audit every discovered layer")
    parser.add_argument("--rounds", type=int, default=2, help="consecutive clean rounds required")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.all:
        layers = _discover_layers()
    elif args.layer:
        layers = [args.layer]
    else:
        parser.error("pass --layer <name> or --all")

    reports = [_run_one(layer, args.rounds) for layer in layers]

    if args.json:
        print(json.dumps([report_to_dict(r) for r in reports], indent=2))
    else:
        for report in reports:
            print(format_report(report))
        held = sum(1 for r in reports if r.held)
        print(f"\n== {held}/{len(reports)} layers HELD across {args.rounds} rounds ==")

    return 0 if all(r.held for r in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
