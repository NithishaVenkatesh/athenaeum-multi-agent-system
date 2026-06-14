"""Smoke the assessment banks *from Azure*: list, download, and validate.

Confirms the cloud copy is present and well-formed. Requires the ``foundry``
dependency group and AZURE_STORAGE_ACCOUNT (auth via DefaultAzureCredential).

Run:  uv run --group foundry python scripts/assessments_azure_smoke.py
"""

from __future__ import annotations

import sys

from app.assessments.azure_blob import list_bank_keys, local_bank_index, pull_bank
from app.assessments.validation import validate_bank


def main() -> int:
    keys = list_bank_keys()
    print(f"== Azure container holds {len(keys)} bank blob(s) ==")
    for key in keys[:5]:
        print(f"  {key}")

    index = local_bank_index()
    if not index:
        print("  (no local banks to cross-check against)")
        return 0 if keys else 1

    # Download a sample and validate it came back well-formed.
    module_id, (course_id, _key) = next(iter(sorted(index.items())))
    bank = pull_bank(course_id, module_id)
    errors = validate_bank(bank)
    ok = not errors and bank["module_id"] == module_id
    print(f"== pulled {module_id}: valid={not errors} ==")
    if errors:
        for e in errors:
            print(f"  ! {e}")

    missing = [k for _m, (_c, k) in index.items() if k not in set(keys)]
    if missing:
        print(f"== WARNING: {len(missing)} local bank(s) not found in Azure ==")
        for k in missing[:5]:
            print(f"  missing: {k}")

    return 0 if ok and not missing else 1


if __name__ == "__main__":
    sys.exit(main())
