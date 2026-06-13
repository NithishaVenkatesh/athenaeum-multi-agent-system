"""Create the Azure AI Search index and upload course documents.

The index carries an integrated `text-embedding-3-large` vectorizer (embeddings are
computed by the search service at index time) plus a semantic configuration — the two
capabilities a Foundry IQ knowledge base builds on. All operations are idempotent.
"""

from __future__ import annotations

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters,
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)

from athenaeum.config import Settings
from athenaeum.models import SearchDocument

SEMANTIC_CONFIG = "athenaeum-semantic"
VECTOR_PROFILE = "athenaeum-hnsw"


def _credential(settings: Settings) -> AzureKeyCredential:
    settings.require("search_endpoint", "search_admin_key")
    return AzureKeyCredential(settings.search_admin_key)


def build_index(settings: Settings) -> SearchIndex:
    """Create or update the index with vector + semantic search. Returns the index."""
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
        SimpleField(name="kind", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(
            name="vertical", type=SearchFieldDataType.String, filterable=True, facetable=True
        ),
        SimpleField(name="course_id", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="title", type=SearchFieldDataType.String),
        SimpleField(name="level", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="cert", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="prereqs", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="grounded_on", type=SearchFieldDataType.String),
        SimpleField(name="source_url", type=SearchFieldDataType.String),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            stored=False,
            vector_search_dimensions=settings.embed_dimensions,
            vector_search_profile_name=VECTOR_PROFILE,
        ),
    ]

    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="athenaeum-hnsw-alg")],
        profiles=[
            VectorSearchProfile(
                name=VECTOR_PROFILE,
                algorithm_configuration_name="athenaeum-hnsw-alg",
                vectorizer_name="athenaeum-aoai",
            )
        ],
        vectorizers=[
            AzureOpenAIVectorizer(
                vectorizer_name="athenaeum-aoai",
                parameters=AzureOpenAIVectorizerParameters(
                    resource_url=settings.azure_openai_endpoint,
                    deployment_name=settings.embed_deployment,
                    model_name=settings.embed_model,
                    api_key=settings.azure_openai_api_key or None,
                ),
            )
        ],
    )

    semantic_search = SemanticSearch(
        default_configuration_name=SEMANTIC_CONFIG,
        configurations=[
            SemanticConfiguration(
                name=SEMANTIC_CONFIG,
                prioritized_fields=SemanticPrioritizedFields(
                    title_field=SemanticField(field_name="title"),
                    content_fields=[SemanticField(field_name="content")],
                    keywords_fields=[SemanticField(field_name="cert")],
                ),
            )
        ],
    )

    index = SearchIndex(
        name=settings.index_name,
        fields=fields,
        vector_search=vector_search,
        semantic_search=semantic_search,
    )
    client = SearchIndexClient(endpoint=settings.search_endpoint, credential=_credential(settings))
    return client.create_or_update_index(index)


def upload_documents(settings: Settings, docs: list[SearchDocument]) -> int:
    """Upload documents to the index. Integrated vectorization embeds `content` server-side.

    The index defines `content_vector` with the AOAI vectorizer, so we send only the text;
    the service computes embeddings on indexing. Returns the number of succeeded uploads.
    """
    client = SearchClient(
        endpoint=settings.search_endpoint,
        index_name=settings.index_name,
        credential=_credential(settings),
    )
    payload = [d.as_index_dict() for d in docs]
    results = client.merge_or_upload_documents(documents=payload)
    succeeded = sum(1 for r in results if r.succeeded)
    return succeeded


def document_count(settings: Settings) -> int:
    """Return the number of documents currently in the index."""
    client = SearchClient(
        endpoint=settings.search_endpoint,
        index_name=settings.index_name,
        credential=_credential(settings),
    )
    return client.get_document_count()
