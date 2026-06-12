---
title: Foundry IQ — working Python SDK recipes (from official cookbooks)
tags: [foundry-iq, sdk, code, howto, mcp]
status: stable
sources:
  - microsoft/iq-series Foundry-IQ cookbooks (episodes 1–3, code cells)
updated: 2026-06-12
related: [foundry-iq, azure-setup]
---

# Foundry IQ SDK recipes (verified against MS cookbooks)

```bash
pip install -U azure-search-documents==12.1.0b1 azure-ai-projects azure-identity python-dotenv
az login   # DefaultAzureCredential needs a signed-in identity with RBAC
```

## 1. Index with vectorizer + semantic config (semantic config is REQUIRED)

```python
from azure.identity import DefaultAzureCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex, SearchField, VectorSearch, VectorSearchProfile,
    HnswAlgorithmConfiguration, AzureOpenAIVectorizer, AzureOpenAIVectorizerParameters,
    SemanticSearch, SemanticConfiguration, SemanticPrioritizedFields, SemanticField,
)

credential = DefaultAzureCredential()
index = SearchIndex(
    name="cert-content",
    fields=[
        SearchField(name="id", type="Edm.String", key=True, filterable=True),
        SearchField(name="title", type="Edm.String", searchable=True),
        SearchField(name="category", type="Edm.String", filterable=True),
        SearchField(name="content", type="Edm.String", searchable=True),
        SearchField(name="content_embedding", type="Collection(Edm.Single)",
                    stored=False, vector_search_dimensions=3072,
                    vector_search_profile_name="hnsw_text_3_large"),
    ],
    vector_search=VectorSearch(
        profiles=[VectorSearchProfile(name="hnsw_text_3_large",
                                      algorithm_configuration_name="alg",
                                      vectorizer_name="aoai_vec")],
        algorithms=[HnswAlgorithmConfiguration(name="alg")],
        vectorizers=[AzureOpenAIVectorizer(
            vectorizer_name="aoai_vec",
            parameters=AzureOpenAIVectorizerParameters(
                resource_url=AOAI_ENDPOINT,
                deployment_name="text-embedding-3-large",
                model_name="text-embedding-3-large"))],
    ),
    semantic_search=SemanticSearch(
        default_configuration_name="semantic_config",
        configurations=[SemanticConfiguration(
            name="semantic_config",
            prioritized_fields=SemanticPrioritizedFields(
                title_field=SemanticField(field_name="title"),
                content_fields=[SemanticField(field_name="content")]))],
    ),
)
index_client = SearchIndexClient(endpoint=SEARCH_ENDPOINT, credential=credential)
index_client.create_or_update_index(index)
```

Upload docs:

```python
from azure.search.documents import SearchIndexingBufferedSender
with SearchIndexingBufferedSender(endpoint=SEARCH_ENDPOINT, index_name="cert-content",
                                  credential=credential) as sender:
    sender.upload_documents(documents=documents)  # list[dict] matching fields
```

## 2. Knowledge sources (indexed / blob / web)

```python
from azure.search.documents.indexes.models import (
    SearchIndexKnowledgeSource, SearchIndexKnowledgeSourceParameters, SearchIndexFieldReference,
    AzureBlobKnowledgeSource, AzureBlobKnowledgeSourceParameters, WebKnowledgeSource,
)

indexed = SearchIndexKnowledgeSource(
    name="cert-index-source", description="Approved certification content",
    search_index_parameters=SearchIndexKnowledgeSourceParameters(
        search_index_name="cert-content",
        source_data_fields=[SearchIndexFieldReference(name="id"),
                            SearchIndexFieldReference(name="title"),
                            SearchIndexFieldReference(name="category")]))

blob = AzureBlobKnowledgeSource(   # Foundry IQ auto-builds the ingestion pipeline
    name="cert-docs-blob-source", description="Synthetic guidance PDFs/markdown",
    azure_blob_parameters=AzureBlobKnowledgeSourceParameters(
        connection_string=BLOB_CONNECTION_STRING, container_name="cert-docs"))

web = WebKnowledgeSource(name="web-source", description="Public exam-page info")

for ks in (indexed, blob, web):
    index_client.create_or_update_knowledge_source(knowledge_source=ks)
```

## 3. Knowledge base (multi-source, answer synthesis)

```python
from azure.search.documents.indexes.models import (
    KnowledgeBase, KnowledgeBaseAzureOpenAIModel, KnowledgeSourceReference,
)
from azure.search.documents.knowledgebases.models import KnowledgeRetrievalOutputMode

kb = KnowledgeBase(
    name="cert-knowledge-base",
    models=[KnowledgeBaseAzureOpenAIModel(
        azure_open_ai_parameters=AzureOpenAIVectorizerParameters(
            resource_url=AOAI_ENDPOINT, deployment_name="gpt-4o-mini", model_name="gpt-4o-mini"))],
    knowledge_sources=[KnowledgeSourceReference(name="cert-index-source"),
                       KnowledgeSourceReference(name="web-source")],
    output_mode=KnowledgeRetrievalOutputMode.ANSWER_SYNTHESIS,
    answer_instructions="Answer concisely, grounded ONLY in retrieved documents, with citations.",
)
index_client.create_or_update_knowledge_base(kb)
```

## 4. Query with reasoning effort + activity log (demo gold)

```python
from azure.search.documents.knowledgebases import KnowledgeBaseRetrievalClient
from azure.search.documents.knowledgebases.models import (
    KnowledgeBaseRetrievalRequest, KnowledgeBaseMessage, KnowledgeBaseMessageTextContent,
    SearchIndexKnowledgeSourceParams,
    KnowledgeRetrievalMinimalReasoningEffort,   # no LLM planning
    KnowledgeRetrievalLowReasoningEffort,       # planning + source selection
    KnowledgeRetrievalMediumReasoningEffort,    # iterative refinement
)

rc = KnowledgeBaseRetrievalClient(endpoint=SEARCH_ENDPOINT,
                                  knowledge_base_name="cert-knowledge-base",
                                  credential=credential)
result = rc.retrieve(retrieval_request=KnowledgeBaseRetrievalRequest(
    messages=[KnowledgeBaseMessage(role="user",
              content=[KnowledgeBaseMessageTextContent(text="Generate 3 AZ-204 practice questions on Azure Functions")])],
    knowledge_source_params=[SearchIndexKnowledgeSourceParams(
        knowledge_source_name="cert-index-source",
        include_references=True, include_reference_source_data=True)],
    include_activity=True,                                  # ← query plan / routing log
    retrieval_reasoning_effort=KnowledgeRetrievalMediumReasoningEffort(),
))

answer = "\n\n".join(c.text for r in result.response for c in r.content)
plan   = [a.as_dict() for a in (result.activity or [])]    # show this in the UI
refs   = result.references                                  # citations
```

## 5. Wire KB into a Foundry agent via MCP

```python
# KB's MCP endpoint
mcp_endpoint = f"{SEARCH_ENDPOINT}/knowledgebases/cert-knowledge-base/mcp?api-version=2025-11-01-Preview"

# (a) project connection via ARM (PUT .../connections/<name>?api-version=2025-10-01-preview)
#     authType=ProjectManagedIdentity, category=RemoteTool, target=mcp_endpoint,
#     audience="https://search.azure.com/"   ← see ep1 cookbook for full payload

# (b) agent with MCPTool
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition, MCPTool

project_client = AIProjectClient(endpoint=FOUNDRY_PROJECT_ENDPOINT, credential=credential)
agent = project_client.agents.create_version(
    agent_name="assessment-agent",
    definition=PromptAgentDefinition(
        model="gpt-4o-mini",
        instructions=(
            "You must use the knowledge base for every answer. Never answer from your own "
            "knowledge. Cite as 【message_idx:search_idx†source_name】. "
            "If the knowledge base lacks the answer, reply \"I don't know\"."),
        tools=[MCPTool(server_label="knowledge-base", server_url=mcp_endpoint,
                       require_approval="never", allowed_tools=["knowledge_base_retrieve"],
                       project_connection_id="cert-kb-mcp-connection")],
    ))

# (c) converse (OpenAI-compatible surface)
openai_client = project_client.get_openai_client()
conv = openai_client.conversations.create()
resp = openai_client.responses.create(
    conversation=conv.id,
    input="Am I ready for AZ-204?",
    extra_body={"agent_reference": {"name": agent.name, "type": "agent_reference"}})
print(resp.output_text)
```

## MCP client configs (VS Code Copilot)

```json
// .vscode/mcp.json
{"servers": {"cert-kb": {"type": "sse",
  "url": "https://<svc>.search.windows.net/knowledgebases/cert-knowledge-base/mcp?api-version=2025-11-01-preview",
  "headers": {"api-key": "${input:search-api-key}"}}}}
```
