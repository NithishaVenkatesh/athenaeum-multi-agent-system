"""Create the Foundry IQ knowledge base over the course index.

Foundry IQ's agentic-retrieval surface (knowledge sources + knowledge base/agent) lives in
the *preview* `azure-search-documents` betas, and class names have drifted across releases.
Rather than hard-pin to one shape, we resolve the classes that the *installed* SDK actually
exposes and build the knowledge base from those. If the installed SDK predates the feature,
we report it clearly — the vector + semantic index built by `search_index` is fully
queryable on its own, so ingestion still produces a working retrieval layer.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass

from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient

from athenaeum.config import Settings


@dataclass
class KnowledgeBaseResult:
    created: bool
    detail: str
    mcp_endpoint: str | None = None


def _resolve(names: tuple[str, ...]) -> dict[str, type]:
    """Return the subset of model classes present in the installed SDK, keyed by name."""
    models = importlib.import_module("azure.search.documents.indexes.models")
    return {n: getattr(models, n) for n in names if hasattr(models, n)}


def build_knowledge_base(settings: Settings) -> KnowledgeBaseResult:
    """Create/refresh a knowledge source over the index and a knowledge base over it.

    Idempotent. Returns a result describing what happened, including the MCP endpoint the
    knowledge base exposes for `knowledge_base_retrieve` so it can be wired into a Foundry agent.
    """
    settings.require("search_endpoint", "search_admin_key")
    client = SearchIndexClient(
        endpoint=settings.search_endpoint,
        credential=AzureKeyCredential(settings.search_admin_key),
    )

    cls = _resolve(
        (
            "SearchIndexKnowledgeSource",
            "SearchIndexKnowledgeSourceParameters",
            "KnowledgeBase",
            "KnowledgeBaseAzureOpenAIModel",
            "KnowledgeSourceReference",
            "AzureOpenAIVectorizerParameters",
            "KnowledgeRetrievalOutputMode",
        )
    )
    required = {
        "SearchIndexKnowledgeSource",
        "SearchIndexKnowledgeSourceParameters",
        "KnowledgeBase",
        "KnowledgeSourceReference",
    }
    missing = required - set(cls)
    if missing:
        return KnowledgeBaseResult(
            created=False,
            detail=(
                "Installed azure-search-documents lacks the Foundry IQ knowledge-base classes "
                f"({', '.join(sorted(missing))}). The vector+semantic index is built and "
                "queryable. To add the managed KB layer, pin a beta exposing these classes "
                "(see release notes) and re-run `athenaeum ingest`."
            ),
        )

    # Knowledge source over the existing index (with the semantic config for ranking).
    from athenaeum.search_index import SEMANTIC_CONFIG

    source_kwargs: dict[str, object] = {
        "search_index_name": settings.index_name,
        "semantic_configuration_name": SEMANTIC_CONFIG,
    }
    ks = cls["SearchIndexKnowledgeSource"](
        name=settings.knowledge_source_name,
        description="Athenaeum synthetic course content (grounded on public MS cert outlines).",
        search_index_parameters=cls["SearchIndexKnowledgeSourceParameters"](**source_kwargs),
    )
    client.create_or_update_knowledge_source(knowledge_source=ks)

    # Knowledge base over the source, with answer synthesis + grounding instructions.
    kb_kwargs: dict[str, object] = {
        "name": settings.knowledge_base_name,
        "knowledge_sources": [cls["KnowledgeSourceReference"](name=settings.knowledge_source_name)],
    }
    if "KnowledgeBaseAzureOpenAIModel" in cls and "AzureOpenAIVectorizerParameters" in cls:
        kb_kwargs["models"] = [
            cls["KnowledgeBaseAzureOpenAIModel"](
                azure_open_ai_parameters=cls["AzureOpenAIVectorizerParameters"](
                    resource_url=settings.azure_openai_endpoint,
                    deployment_name=settings.gpt_deployment,
                    model_name=settings.gpt_deployment,
                    api_key=settings.azure_openai_api_key or None,
                )
            )
        ]
    if "KnowledgeRetrievalOutputMode" in cls:
        mode = cls["KnowledgeRetrievalOutputMode"]
        kb_kwargs["output_mode"] = getattr(mode, "ANSWER_SYNTHESIS", None) or getattr(
            mode, "answer_synthesis", None
        )
    kb_kwargs["answer_instructions"] = (
        "Answer only from the retrieved Athenaeum course documents, and cite the source. "
        "If the knowledge base does not contain the answer, say you don't know."
    )

    kb = cls["KnowledgeBase"](**{k: v for k, v in kb_kwargs.items() if v is not None})
    client.create_or_update_knowledge_base(kb)

    mcp = (
        f"{settings.search_endpoint}/knowledgebases/{settings.knowledge_base_name}"
        f"/mcp?api-version={settings.search_api_version}"
    )
    return KnowledgeBaseResult(
        created=True,
        detail=f"Knowledge base '{settings.knowledge_base_name}' created over "
        f"'{settings.knowledge_source_name}'.",
        mcp_endpoint=mcp,
    )
