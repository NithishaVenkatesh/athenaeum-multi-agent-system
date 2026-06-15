"""Azure Blob mirror for the assessment question banks.

The banks' system of record is the JSON under ``ayanakoji/assessments/banks`` (and
the seeded SQLite DB). This module pushes those JSON files to an Azure Blob
container and reads them back, so the banks have a cloud copy independent of the
repo.

Auth is ``DefaultAzureCredential`` (no secrets in the repo); the Azure SDK lives
in the optional ``foundry`` dependency group and is imported lazily, so importing
this module never requires the SDK. Functions accept an injected ``client`` so
they can be unit-tested without Azure installed or reachable.

Blob key layout mirrors the repo: ``banks/<course_id>/<module_id>.json``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol, cast

from app.assessments.loader import banks_dir, iter_bank_files
from app.assessments.validation import validate_bank
from app.config import get_settings


class _BlobClient(Protocol):
    """The slice of azure-storage-blob's BlobServiceClient that we use."""

    def get_blob_client(self, container: str, blob: str) -> Any: ...
    def get_container_client(self, container: str) -> Any: ...


def blob_key(course_id: str, module_id: str) -> str:
    """The blob key for a module's bank JSON."""
    return f"banks/{course_id}/{module_id}.json"


def build_client(account: str | None = None) -> _BlobClient:
    """Build a real BlobServiceClient via DefaultAzureCredential (lazy SDK import)."""
    account = account or get_settings().azure_storage_account
    if not account:
        raise RuntimeError(
            "AZURE_STORAGE_ACCOUNT is not configured — cannot reach Azure Blob storage."
        )
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient

    url = f"https://{account}.blob.core.windows.net"
    # The SDK is untyped in some resolutions (mypy sees Any) — cast to the Protocol
    # we declare so the return type is honoured regardless of stub availability.
    client = BlobServiceClient(account_url=url, credential=DefaultAzureCredential())
    return cast(_BlobClient, client)


def push_banks(
    *, client: _BlobClient | None = None, container: str | None = None, root: Path | None = None
) -> dict[str, Any]:
    """Upload every bank JSON to the container. Returns a summary; validates first."""
    client = client or build_client()
    container = container or get_settings().assessment_blob_container
    uploaded: list[str] = []
    for path in iter_bank_files(root):
        bank = json.loads(path.read_text(encoding="utf-8"))
        errors = validate_bank(bank)
        if errors:
            raise ValueError(f"{path.name}: refusing to push invalid bank: {errors}")
        key = blob_key(bank["course_id"], bank["module_id"])
        data = json.dumps(bank, ensure_ascii=False, indent=2).encode("utf-8")
        client.get_blob_client(container, key).upload_blob(data, overwrite=True)
        uploaded.append(key)
    return {"container": container, "uploaded": len(uploaded), "keys": uploaded}


def list_bank_keys(*, client: _BlobClient | None = None, container: str | None = None) -> list[str]:
    """List the bank blob keys in the container."""
    client = client or build_client()
    container = container or get_settings().assessment_blob_container
    cc = client.get_container_client(container)
    return sorted(b.name for b in cc.list_blobs(name_starts_with="banks/"))


def pull_bank(
    course_id: str,
    module_id: str,
    *,
    client: _BlobClient | None = None,
    container: str | None = None,
) -> dict[str, Any]:
    """Download and parse one module's bank JSON from the container."""
    client = client or build_client()
    container = container or get_settings().assessment_blob_container
    blob = client.get_blob_client(container, blob_key(course_id, module_id))
    raw = blob.download_blob().readall()
    data: dict[str, Any] = json.loads(raw)
    return data


def pull_all_banks(
    *, client: _BlobClient | None = None, container: str | None = None
) -> list[dict[str, Any]]:
    """Download and parse every bank JSON in the container (the startup seed source).

    Returns the banks sorted by blob key for determinism. Validation is left to the
    seeding step so there is a single place that decides what is loadable.
    """
    client = client or build_client()
    container = container or get_settings().assessment_blob_container
    banks: list[dict[str, Any]] = []
    for key in list_bank_keys(client=client, container=container):
        raw = client.get_blob_client(container, key).download_blob().readall()
        banks.append(json.loads(raw))
    return banks


def local_bank_index(root: Path | None = None) -> dict[str, tuple[str, str]]:
    """Map module_id -> (course_id, blob_key) for every local bank (smoke helper)."""
    index: dict[str, tuple[str, str]] = {}
    for path in iter_bank_files(root or banks_dir()):
        bank = json.loads(path.read_text(encoding="utf-8"))
        index[bank["module_id"]] = (
            bank["course_id"],
            blob_key(bank["course_id"], bank["module_id"]),
        )
    return index
