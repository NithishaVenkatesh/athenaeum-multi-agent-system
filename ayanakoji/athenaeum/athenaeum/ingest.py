"""Ingestion orchestration: validate -> build index -> upload docs -> build Foundry IQ KB.

This is the one entry point that mutates Azure. It refuses to run on invalid content and
retries transient Azure failures, so a single `athenaeum ingest` is safe to re-run.
"""

from __future__ import annotations

from dataclasses import dataclass

from azure.core.exceptions import HttpResponseError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from athenaeum import content, search_index
from athenaeum.config import Settings
from athenaeum.knowledge_base import KnowledgeBaseResult, build_knowledge_base


@dataclass
class IngestResult:
    documents_uploaded: int
    index_name: str
    kb: KnowledgeBaseResult


_retry = retry(
    retry=retry_if_exception_type(HttpResponseError),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=20),
    reraise=True,
)


@_retry
def _build_index(settings: Settings) -> None:
    search_index.build_index(settings)


@_retry
def _upload(settings: Settings, docs: list[content.SearchDocument]) -> int:
    return search_index.upload_documents(settings, docs)


def run(settings: Settings) -> IngestResult:
    """Validate content, then build the index, upload documents, and build the KB."""
    report = content.validate()
    if not report.ok:
        raise RuntimeError(
            f"Refusing to ingest: {len(report.errors)} content error(s). Run `athenaeum validate`."
        )

    docs = content.build_documents()
    _build_index(settings)
    uploaded = _upload(settings, docs)
    kb = build_knowledge_base(settings)
    return IngestResult(documents_uploaded=uploaded, index_name=settings.index_name, kb=kb)
