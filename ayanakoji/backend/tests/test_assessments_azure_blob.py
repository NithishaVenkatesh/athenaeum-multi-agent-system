"""Tests for the Azure Blob mirror using an in-memory fake client (no SDK needed).

``azure_blob`` imports the Azure SDK lazily inside ``build_client`` only, so these
tests inject a fake client and never require ``azure-storage-blob`` to be present.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.assessments.azure_blob import blob_key, build_client, list_bank_keys, pull_bank, push_banks

from tests.test_assessments_loader import _write_banks
from tests.test_assessments_validation import make_valid_bank


class _FakeBlob:
    def __init__(self, store: dict[str, bytes], key: str) -> None:
        self._store = store
        self._key = key

    def upload_blob(self, data: bytes, overwrite: bool = False) -> None:
        if self._key in self._store and not overwrite:
            raise FileExistsError(self._key)
        self._store[self._key] = data

    def download_blob(self) -> _FakeDownload:
        return _FakeDownload(self._store[self._key])


class _FakeDownload:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def readall(self) -> bytes:
        return self._data


class _FakeBlobName:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeContainer:
    def __init__(self, store: dict[str, bytes]) -> None:
        self._store = store

    def list_blobs(self, name_starts_with: str = "") -> list[_FakeBlobName]:
        return [_FakeBlobName(k) for k in self._store if k.startswith(name_starts_with)]


class FakeBlobServiceClient:
    """Records uploads into an in-memory dict keyed by blob key."""

    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}

    def get_blob_client(self, container: str, blob: str) -> _FakeBlob:
        return _FakeBlob(self.store, blob)

    def get_container_client(self, container: str) -> _FakeContainer:
        return _FakeContainer(self.store)


def test_push_uploads_one_blob_per_bank(tmp_path: Path) -> None:
    _write_banks(
        tmp_path, [make_valid_bank("cb-c01", "cb-c01-m01"), make_valid_bank("cb-c02", "cb-c02-m01")]
    )
    client = FakeBlobServiceClient()
    summary = push_banks(client=client, container="assessment-banks", root=tmp_path)
    assert summary["uploaded"] == 2
    assert set(summary["keys"]) == {
        blob_key("cb-c01", "cb-c01-m01"),
        blob_key("cb-c02", "cb-c02-m01"),
    }
    assert set(client.store) == set(summary["keys"])


def test_pushed_blob_roundtrips_through_pull(tmp_path: Path) -> None:
    _write_banks(tmp_path, [make_valid_bank("cb-c01", "cb-c01-m01")])
    client = FakeBlobServiceClient()
    push_banks(client=client, container="c", root=tmp_path)
    bank = pull_bank("cb-c01", "cb-c01-m01", client=client, container="c")
    assert bank["module_id"] == "cb-c01-m01"
    assert len(bank["choices"]) == 5
    assert len(bank["llm"]) == 3


def test_list_bank_keys(tmp_path: Path) -> None:
    _write_banks(
        tmp_path, [make_valid_bank("cb-c01", "cb-c01-m01"), make_valid_bank("cb-c01", "cb-c01-m02")]
    )
    client = FakeBlobServiceClient()
    push_banks(client=client, container="c", root=tmp_path)
    keys = list_bank_keys(client=client, container="c")
    assert keys == [blob_key("cb-c01", "cb-c01-m01"), blob_key("cb-c01", "cb-c01-m02")]


def test_push_refuses_invalid_bank(tmp_path: Path) -> None:
    bad = make_valid_bank()
    bad["choices"][0]["correct_answers"] = ["nope"]
    _write_banks(tmp_path, [bad])
    client = FakeBlobServiceClient()
    with pytest.raises(ValueError, match="invalid bank"):
        push_banks(client=client, container="c", root=tmp_path)


def test_build_client_without_account_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AZURE_STORAGE_ACCOUNT", raising=False)
    with pytest.raises(RuntimeError, match="AZURE_STORAGE_ACCOUNT"):
        build_client(account=None)


def test_blob_key_layout() -> None:
    assert blob_key("cb-c01", "cb-c01-m03") == "banks/cb-c01/cb-c01-m03.json"
