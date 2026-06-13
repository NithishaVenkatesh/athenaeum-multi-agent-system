"""Manual Foundry connectivity smoke test.

Run:  uv run --group foundry python scripts/foundry_smoke.py
Reads credentials from the git-ignored .env. Costs ~0 (<=5 output tokens).
"""

from __future__ import annotations

import sys

from app.foundry import project_check, smoke_check


def main() -> int:
    print("== Azure OpenAI chat completion (API key) ==")
    aoai = smoke_check()
    print(f"  ok={aoai.ok}  model={aoai.model}")
    print(f"  detail: {aoai.detail}")
    if aoai.reply is not None:
        print(f"  reply: {aoai.reply!r}")

    print("\n== Foundry project (DefaultAzureCredential) ==")
    proj = project_check()
    print(f"  ok={proj.ok}")
    print(f"  detail: {proj.detail}")

    # The API-key OpenAI path is the gate; the project path is best-effort (RBAC-dependent).
    return 0 if aoai.ok else 1


if __name__ == "__main__":
    sys.exit(main())
