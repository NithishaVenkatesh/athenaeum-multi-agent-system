"""Push the assessment question banks to Azure Blob storage.

The pipeline that gets the authored JSON banks into Azure. Requires the
``foundry`` dependency group and AZURE_STORAGE_ACCOUNT (auth via
DefaultAzureCredential). Validates every bank before uploading.

Run:  uv run --group foundry python scripts/assessments_push.py
"""

from __future__ import annotations

import sys

from app.assessments.azure_blob import push_banks


def main() -> int:
    summary = push_banks()
    print(f"== Pushed {summary['uploaded']} banks to container '{summary['container']}' ==")
    for key in summary["keys"][:5]:
        print(f"  {key}")
    if summary["uploaded"] > 5:
        print(f"  … (+{summary['uploaded'] - 5} more)")
    return 0 if summary["uploaded"] else 1


if __name__ == "__main__":
    sys.exit(main())
