# Azure AI Foundry & External Tools: Complete Agentic Enhancement Research Report

*Generated: 2026-06-14 | Sources: 40+ | Confidence: High*
*Context: MSF Reasoning Agent — Reasoning Agents Challenge A*

---

## Executive Summary

This report covers every Azure AI Foundry SDK tool and relevant external API for hardening an agentic system across eight dimensions: **accuracy, reliability, safety, relevance, multi-step reasoning, evaluation, observability, and memory/grounding**. The Foundry ecosystem is now Generally Available (GA as of early 2026) and provides a near-complete native stack. External frameworks fill gaps in structured output enforcement, offline safety classification, and framework-agnostic observability.

**Key takeaways:**
- The `azure-ai-evaluation` SDK has 30+ evaluators including 8 purpose-built agentic evaluators (tool call accuracy, intent resolution, task adherence, task navigation efficiency)
- Azure AI Content Safety provides a 5-layer defense: input jailbreak detection, document injection detection, harm classification, groundedness detection, and the new Task Adherence API
- Azure AI Search's Agentic Retrieval (GA, REST 2026-04-01) performs LLM-planned multi-subquery decomposition before retrieval — the strongest native RAG path
- The `ConnectedAgentTool` pattern enables server-side multi-agent delegation without round-trips through client code
- For external observability, Langfuse (open-source, MIT) and Arize Phoenix (ELv2, self-hostable) are the top picks for non-LangChain stacks
- LlamaGuard 4 (12B, multimodal, April 2025) is the best drop-in safety classifier for pre/post-LLM filtering
- RAGAS is the strongest external evaluation framework with 30+ metrics including agentic tool call accuracy and goal achievement

---

## Part A: Azure AI Foundry SDK — Native Capabilities

### A1. Evaluation & Testing

**Package:** `pip install azure-ai-evaluation "azure-ai-projects>=2.2.0"`

#### Complete Built-in Evaluator Catalog

**General-purpose evaluators** (`azure.ai.evaluation`):

| Class | Measures | Inputs |
|---|---|---|
| `CoherenceEvaluator` | Logical flow and organization | `query`, `response` |
| `FluencyEvaluator` | Grammar, readability | `response` |
| `RelevanceEvaluator` | Relevance of response to query | `query`, `response` |
| `QAEvaluator` | Composite: groundedness + relevance + coherence + fluency | `query`, `response`, `ground_truth` |

**RAG / retrieval evaluators:**

| Class | Measures | Notes |
|---|---|---|
| `GroundednessEvaluator` | Response grounded in context | Requires `context` field |
| `GroundednessProEvaluator` | Enhanced via Azure AI Content Safety backend | Requires `azure_ai_project` |
| `RetrievalEvaluator` | Quality of retrieved context | Conversation format |
| `DocumentRetrievalEvaluator` | Document retrieval quality | Needs `ground_truth` |
| `ResponseCompletenessEvaluator` | Whether response fully addresses query | Needs `ground_truth` |

**NLP similarity (no LLM, deterministic):**

`SimilarityEvaluator`, `F1ScoreEvaluator`, `BleuScoreEvaluator`, `GleuScoreEvaluator`, `RougeScoreEvaluator`, `MeteorScoreEvaluator`

**Risk and safety evaluators** (require `azure_ai_project`, not `model_config`):

| Class | Detects |
|---|---|
| `ViolenceEvaluator` | Physical violence |
| `SexualEvaluator` | Sexual content |
| `SelfHarmEvaluator` | Self-harm content |
| `HateUnfairnessEvaluator` | Hate speech |
| `IndirectAttackEvaluator` | Cross-domain prompt injection (XPIA) |
| `ProtectedMaterialEvaluator` | Copyright/IP violations |
| `CodeVulnerabilityEvaluator` | SQL injection, code injection (7 languages) |
| `ContentSafetyEvaluator` | Composite: violence + sexual + self-harm + hate |

#### Agentic Evaluators (Purpose-Built for Agent Pipelines)

All take `query`, `response`, and `tool_definitions` (OpenAI function-calling schema). Return Pass/Fail binary.

**System evaluators (end-to-end outcomes):**

| Class | Builtin Name | Purpose |
|---|---|---|
| `IntentResolutionEvaluator` | `builtin.intent_resolution` | Did agent correctly identify user intent? |
| `TaskAdherenceEvaluator` | `builtin.task_adherence` | Did agent follow rules, system prompt, procedures? |
| `TaskCompletionEvaluator` | `builtin.task_completion` | Did agent deliver a usable deliverable? |
| `CustomerSatisfactionEvaluator` | `builtin.customer_satisfaction` | Holistic satisfaction: clarity, tone, resolution |
| `TaskNavigationEfficiencyEvaluator` | `builtin.task_navigation_efficiency` | Optimal tool-call path vs. ground-truth sequence |

**Process evaluators (tool-call level):**

| Class | Builtin Name | Purpose |
|---|---|---|
| `ToolCallAccuracyEvaluator` | `builtin.tool_call_accuracy` | Correct tools + correct parameters, no redundancy |
| `ToolSelectionEvaluator` | `builtin.tool_selection` | Correct tool selected, no unnecessary tools |
| `ToolInputAccuracyEvaluator` | `builtin.tool_input_accuracy` | All params correct across 6 criteria |
| `ToolOutputUtilizationEvaluator` | `builtin.tool_output_utilization` | Agent used tool results in reasoning |
| `ToolCallSuccessEvaluator` | `builtin.tool_call_success` | Tool calls succeeded without exceptions |

**Quality grader (preview):** `builtin.quality_grader` — relevance, abstention, answer completeness, groundedness + context coverage in one call (same evaluator used by Microsoft Copilot Studio).

#### Running Evaluations

```python
from azure.ai.evaluation import evaluate, GroundednessEvaluator, AzureOpenAIModelConfiguration

model_config = AzureOpenAIModelConfiguration(
    azure_endpoint=os.environ["AZURE_ENDPOINT"],
    api_key=os.environ["AZURE_API_KEY"],
    azure_deployment=os.environ["AZURE_DEPLOYMENT_NAME"],
    api_version=os.environ["AZURE_API_VERSION"],
)
groundedness_eval = GroundednessEvaluator(model_config)

# Batch evaluation over JSONL file
result = evaluate(
    data="data.jsonl",
    evaluators={"groundedness": groundedness_eval},
    evaluator_config={
        "groundedness": {
            "column_mapping": {
                "query": "${data.queries}",
                "context": "${data.context}",
                "response": "${data.response}"
            }
        }
    },
    azure_ai_project=azure_ai_project,  # logs to Foundry portal
    output_path="./evalresults.json"
)
# Access result.studio_url for portal link
```

#### Cloud Evaluation (AIProjectClient + OpenAI Evals API)

```python
from azure.ai.projects import AIProjectClient
project_client = AIProjectClient(
    endpoint="https://<resource>.services.ai.azure.com/api/projects/<project>",
    credential=DefaultAzureCredential(),
)
openai_client = project_client.get_openai_client()

eval = openai_client.evals.create(name=..., data_source_config=..., testing_criteria=...)
run = openai_client.evals.runs.create(eval_id=eval.id, name=..., data_source=...)
```

Data source types: uploaded JSONL, live model target, live agent target, Application Insights traces (`azure_ai_trace_data_source_preview`), synthetic data gen.

#### AI Red Teaming Agent (PyRIT-backed)

Key metric: **Attack Success Rate (ASR)** = successful attacks / total.

Supported attack categories:
- All models: Hateful/Unfair, Sexual, Violent, Self-Harm, Protected Materials, Code Vulnerability, Ungrounded Attributes
- Agents only: Prohibited Actions, Sensitive Data Leakage, Task Adherence, Indirect Prompt Injection (XPIA via tool outputs)

30+ attack strategies: `AnsiAttack`, `Base64`, `Caesar`, `Flip`, `Jailbreak`, `IndirectJailbreak`, `Leetspeak`, `Crescendo` (multi-turn escalation), `ROT13`, `UnicodeConfusable`, `SuffixAppend`, and more.

Cloud red-teaming regions: East US 2, France Central, Sweden Central, Switzerland West, US North Central.

**Docs:** https://learn.microsoft.com/en-us/azure/foundry/concepts/ai-red-teaming-agent

#### Custom Evaluators

Two types, registered via `project_client.beta.evaluators.create_version()`:

- **Code-based:** Python function returning `0.0–1.0`. Available packages include numpy, pandas, scikit-learn, rapidfuzz, sympy, rouge-score.
- **Prompt-based:** Judge prompt with `{{variable}}` syntax. Scoring: `ordinal` (1–N), `continuous` (float), `binary`. Must return `{"result": ..., "reason": "..."}`.

---

### A2. Tracing & Observability

**Packages:**
```bash
pip install "azure-ai-inference[opentelemetry]"
pip install azure-monitor-opentelemetry
pip install opentelemetry-instrumentation-openai-v2
pip install opentelemetry-instrumentation-openai-agents
pip install microsoft-opentelemetry   # for LangChain/LangGraph
```

#### AIInferenceInstrumentor (Core)

```python
from azure.core.settings import settings
settings.tracing_implementation = "opentelemetry"
# OR: set AZURE_SDK_TRACING_IMPLEMENTATION=opentelemetry

from azure.ai.inference.tracing import AIInferenceInstrumentor
AIInferenceInstrumentor().instrument()
# ... make inference calls ...
AIInferenceInstrumentor().uninstrument()
```

**Key environment variables:**

| Variable | Purpose |
|---|---|
| `AZURE_SDK_TRACING_IMPLEMENTATION` | Set to `opentelemetry` |
| `AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED` | `true` — captures prompt/completion content |
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` | `true` or `SPAN_AND_EVENT` |
| `OTEL_SEMCONV_STABILITY_OPT_IN` | `gen_ai_latest_experimental` — latest GenAI semconv |

By default, prompts, completions, tool names, and parameters are **not** recorded. Content capture is an explicit opt-in.

#### OTel Span Attributes Emitted

```json
{
  "gen_ai.operation.name": "chat",
  "gen_ai.system": "openai",
  "gen_ai.request.model": "gpt-4o",
  "gen_ai.response.finish_reasons": ["stop"],
  "gen_ai.usage.input_tokens": 14,
  "gen_ai.usage.output_tokens": 91
}
```

Token usage is always present. Tool call details appear when content recording is enabled.

#### Application Insights as Trace Backend

```python
from azure.ai.projects import AIProjectClient
project_client = AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=DefaultAzureCredential())
conn_str = project_client.telemetry.get_application_insights_connection_string()

from azure.monitor.opentelemetry import configure_azure_monitor
configure_azure_monitor(connection_string=conn_str)

from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
OpenAIInstrumentor().instrument()
```

Traces retained 90 days in Foundry portal. Data retention follows your Log Analytics workspace configuration.

#### Framework-Specific Instrumentation

```python
# OpenAI Agents SDK
from opentelemetry.instrumentation.openai_agents import OpenAIAgentsInstrumentor
OpenAIAgentsInstrumentor().instrument(tracer_provider=trace.get_tracer_provider())

# LangChain / LangGraph (Microsoft OTel distro)
from microsoft.opentelemetry import use_microsoft_opentelemetry
use_microsoft_opentelemetry(
    enable_azure_monitor=True,
    instrumentation_options={"langchain": {"enabled": True, "agent_id": "my_agent_id"}},
)
```

#### Portal Trace Viewer

**Foundry portal path:** Observability → Traces
- Full execution timeline, inputs/outputs per span, latency, errors
- Conversation view: dialogue history, response tokens, ordered tool calls
- Filter: "View Traces with Agent Runs" / "View Traces with Gen AI Errors"

**Azure Monitor path:** App Insights resource → Agents (Preview)
- End-to-end story view: agent → LLM → tool calls
- Sort by "Most tokens used"
- Pre-built Grafana dashboards available

#### Custom Spans

```python
from opentelemetry import trace
tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("my_operation")
def my_function(param):
    trace.get_current_span().set_attribute("operation.item_count", len(param))
```

**Docs:** https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/trace-agent-setup

---

### A3. Safety & Content Filtering

**Package:** `pip install azure-ai-contentsafety`
**API version (GA):** `2024-09-01`
**Base endpoint:** `{CONTENT_SAFETY_ENDPOINT}/contentsafety/`

#### Harm Category Analysis

```python
from azure.ai.contentsafety import ContentSafetyClient
from azure.ai.contentsafety.models import AnalyzeTextOptions, TextCategory

client = ContentSafetyClient(endpoint, credential)
result = client.analyze_text(AnalyzeTextOptions(
    text=user_input,
    categories=[TextCategory.HATE, TextCategory.VIOLENCE, TextCategory.SEXUAL, TextCategory.SELF_HARM],
    output_type="EightSeverityLevels"   # 0-7 scale
))
# result.categories_analysis[n].severity
```

Four categories: **Hate and Fairness**, **Sexual**, **Violence**, **Self-Harm**. Severity scale: 0–7 (EightSeverityLevels) or 0/2/4/6 (FourSeverityLevels). Image analysis: max 4MB, formats JPEG/PNG/GIF/BMP/TIFF/WEBP.

**Fifth category (new, agent-specific): Task Adherence** — detects misaligned or premature tool invocations by AI agents.

#### Prompt Shields (Jailbreak + Indirect Injection)

```python
# POST {endpoint}/contentsafety/text:shieldPrompt
result = client.shield_prompt(
    user_prompt=user_input,          # direct jailbreak attacks
    documents=[retrieved_chunk_1, retrieved_chunk_2]  # indirect injection in RAG content
)
# result.user_prompt_analysis.attack_detected → bool
# result.documents_analysis[n].attack_detected → bool
```

**User prompt shield** detects: role-play attacks, encoding attacks (base64, ciphers), conversation mockup embedding, system-rule override attempts.

**Document shield** (cross-domain / indirect injection) detects: manipulated content, system intrusion, data exfiltration commands, fraud, malware links, encoding attacks within documents.

**Critical for RAG agents:** Call document shield on every retrieved chunk before injecting into the LLM context.

#### Groundedness Detection (Preview)

```python
# POST {endpoint}/contentsafety/text:detectGroundedness
result = client.detect_groundedness(
    domain="Generic",      # or "Medical"
    task="QnA",            # or "Summarization"
    qna={"query": "What is the rate?"},
    text="The rate is 5%.",
    grounding_sources=["As of July 2024, the rate is 4.5%."],
    reasoning=True         # returns explanation of why ungrounded
)
```

- Limits: 55,000 chars sources, 7,500 chars response, English only
- Modes: Non-Reasoning (fast, binary) or Reasoning (slower, returns explanation)
- **Groundedness Correction:** Pass `correction=True` to get auto-corrected `corrected_text` based on source material
- Rate limit: 50 RPS on S0 tier (most rate-limited API — plan queuing)

#### Protected Material Detection

```python
# POST {endpoint}/contentsafety/text:detectProtectedMaterial
# Detects known copyrighted text (lyrics, articles, code) in LLM output
```
Max 10K chars, min 110 chars, English only. Also has Protected Material for Code variant.

#### Recommended Agent Pipeline Defense Layers

1. **Pre-LLM (user input gate):** `shieldPrompt` with `userPrompt` — detect jailbreaks before agent processes
2. **Post-retrieval:** `shieldPrompt` with `documents` on all retrieved chunks — block indirect injection
3. **Post-LLM (output gate):** `analyze_text` for harm categories + `detectProtectedMaterial` for copyright
4. **Factual accuracy:** `detectGroundedness` on LLM responses against source material
5. **Tool-call validation:** Task Adherence API — verify tool invocations match user intent
6. **Offline red-teaming:** Foundry safety evaluations + adversarial simulator pre-deployment

**Region note:** Only **East US** and **East US 2** support all features simultaneously. Plan resource location accordingly.

**Docs:** https://learn.microsoft.com/en-us/azure/ai-services/content-safety/overview

---

### A4. Grounding, RAG & Memory

#### Architecture: Three Composable RAG Layers

| Layer | Service | What it provides |
|---|---|---|
| File Search (built-in) | Foundry Agent Service | Managed vector store, auto-ingestion, per-agent file search |
| Azure AI Search (Agentic Retrieval) | Azure AI Search | LLM-planned multi-subquery pipeline, MCP endpoint |
| Foundry IQ | Microsoft Foundry Portal | Portal-facing knowledge layer backed by Agentic Retrieval |

#### Foundry Agent File Search Tool

**Package:** `pip install azure-ai-projects`

```python
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import FileSearchTool, PromptAgentDefinition

project = AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=DefaultAzureCredential())
openai = project.get_openai_client()

vector_store = openai.vector_stores.create(name="MyStore")
openai.vector_stores.files.upload_and_poll(vector_store_id=vector_store.id, file=file_handle)

agent = project.agents.create_version(
    agent_name="MyAgent",
    definition=PromptAgentDefinition(
        model="gpt-4o",
        tools=[FileSearchTool(vector_store_ids=[vector_store.id])],
    ),
)
```

**Default settings:**

| Setting | Value |
|---|---|
| Chunk size | 800 tokens |
| Chunk overlap | 400 tokens |
| Embedding model | `text-embedding-3-large` (256 dims) |
| Max chunks in context | 20 |
| Max files per vector store | 10,000 |
| Max file size | 512 MB |

Internal pipeline: query rewrite → complex query decomposition → hybrid search → reranking.

**Setup modes:**
- **Basic:** Microsoft-managed storage and search
- **Standard:** Your own Azure Blob Storage + Azure AI Search (recommended for data sovereignty)

**Supported file types:** `.pdf`, `.docx`, `.pptx`, `.md`, `.txt`, `.py`, `.js`, `.ts`, `.java`, `.cs`, `.cpp`, `.html`, `.json`

#### Azure AI Search — Agentic Retrieval

**GA status:** REST API `2026-04-01`. MCP endpoint in preview.

**Key concepts:**
- **Knowledge Base:** Orchestrates the multi-query pipeline; has an MCP endpoint for direct Foundry agent wiring
- **Knowledge Source:** Your indexed data or a remote source
- **Retrieval reasoning effort:** `minimal` (no LLM planning), `low` (default, LLM plans), `medium` (more expansion)

**Pipeline:** App calls knowledge base → LLM decomposes query into focused subqueries → all subqueries run in parallel (keyword/vector/hybrid) → results semantically reranked (L2) → unified grounding response with citations.

```http
POST /knowledgebases/{name}/retrieve
```

**Python samples:** https://github.com/Azure-Samples/azure-search-python-samples/tree/main/Quickstart-Agentic-Retrieval

#### Hybrid Search (BM25 + Vector + Semantic Ranking)

```http
POST https://{service}.search.windows.net/indexes/{index}/docs/search?api-version=2026-04-01
{
  "search": "historic hotel walk to restaurants",
  "vectorQueries": [
    {"kind": "vector", "vector": [...], "k": 50, "fields": "DescriptionVector", "exhaustive": true}
  ],
  "queryType": "semantic",
  "semanticConfiguration": "my-semantic-config",
  "top": 10
}
```

- BM25 (keyword) + HNSW/eKNN (vector) merged via **Reciprocal Rank Fusion (RRF)**
- Optional L2 semantic reranker (`queryType: "semantic"`) on top of RRF results
- Response includes `@search.score` (RRF) and `@search.rerankerScore` (semantic, 0–4)

Key parameters: `vectorQueries[].k` (set 50 when using semantic ranker), `vectorQueries[].exhaustive` (`true` = exact eKNN), `vectorFilterMode` (`preFilter` or `postFilter`).

#### Integrated Vectorization (Auto-embedding Pipeline)

Pipeline: **Indexer** (data source) → **Skillset** (`TextSplit` + `AzureOpenAIEmbedding`) → **Index** (vector fields + vectorizer).

Supported embedding models via `AzureOpenAIEmbedding` skill:
- `text-embedding-ada-002` (1536 dims)
- `text-embedding-3-small` (1536 dims, reducible)
- `text-embedding-3-large` (3072 dims, reducible)

At query time, vectorizer auto-converts plain text to vectors — no embedding call needed in application code.

---

### A5. Multi-Agent Orchestration & Model Routing

**Packages:**
```bash
pip install "azure-ai-projects>=2.0.0"
pip install azure-ai-agents
pip install semantic-kernel
```

**Endpoint format (v2):** `https://<resource>.services.ai.azure.com/api/projects/<project>`

#### Core Agent Lifecycle

```python
from azure.ai.agents import AgentsClient

agents_client = AgentsClient(endpoint=PROJECT_ENDPOINT, credential=DefaultAzureCredential())

agent = agents_client.create_agent(
    model="gpt-4o",
    name="my-agent",
    instructions="You are a helpful assistant.",
    tools=toolset.definitions,
    tool_resources=toolset.resources
)

thread = agents_client.threads.create()
agents_client.messages.create(thread_id=thread.id, role="user", content="Hello")

# Auto-execute function tools + poll until done
run = agents_client.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)

messages = agents_client.messages.list(thread_id=thread.id, order=ListSortOrder.ASCENDING)
```

#### Built-in Tools

**CodeInterpreterTool** — sandboxed Python execution:
```python
from azure.ai.agents.models import CodeInterpreterTool
code_interpreter = CodeInterpreterTool(file_ids=[uploaded_file.id])
```

**FileSearchTool** — RAG over vector stores:
```python
from azure.ai.agents.models import FileSearchTool
file_search = FileSearchTool(vector_store_ids=[vector_store.id])
```

**BingGroundingTool** — real-time web data:
```python
from azure.ai.agents.models import BingGroundingTool, BingGroundingSearchToolParameters
bing = BingGroundingTool(bing_grounding=BingGroundingSearchToolParameters(
    search_configurations=[BingGroundingSearchConfiguration(connection_id=bing_conn.id)]
))
```

**AzureAISearchTool** — enterprise search:
```python
from azure.ai.agents.models import AzureAISearchTool, AzureAISearchQueryType
ai_search = AzureAISearchTool(index_connection_id=conn_id, index_name="my_index",
                               query_type=AzureAISearchQueryType.SIMPLE, top_k=3)
```

**FunctionTool** — custom Python callable with auto-dispatch:
```python
from azure.ai.agents.models import FunctionTool
functions = FunctionTool({get_weather, lookup_order})
toolset = ToolSet()
toolset.add(functions)
agents_client.enable_auto_function_calls(toolset)
```

**McpTool** — remote MCP server:
```python
from azure.ai.agents.models import McpTool
mcp_tool = McpTool(server_label="devops", server_url="https://mcp.example.com", allowed_tools=[])
mcp_tool.allow_tool("create_workitem")
```

**OpenApiTool** — REST APIs via OpenAPI spec.

**DeepResearchTool** — deep web research (requires `o3-deep-research` model deployment):
```python
from azure.ai.agents.models import DeepResearchTool
deep_research = DeepResearchTool(
    bing_grounding_connection_id=bing_conn.id,
    deep_research_model=os.environ["DEEP_RESEARCH_MODEL_DEPLOYMENT_NAME"]
)
```

#### Multi-Agent: ConnectedAgentTool (Server-Side Hand-off)

The native Foundry pattern. Orchestrator delegates to specialist agents at the service layer — no client round-trips.

```python
from azure.ai.agents.models import ConnectedAgentTool

stock_agent = agents_client.create_agent(model="gpt-4o-mini", name="stocks", instructions="...")
weather_agent = agents_client.create_agent(model="gpt-4o-mini", name="weather", instructions="...")

connected_stock = ConnectedAgentTool(id=stock_agent.id, name="stocks", description="Look up stock prices")
connected_weather = ConnectedAgentTool(id=weather_agent.id, name="weather", description="Get current weather")

orchestrator = agents_client.create_agent(
    model="gpt-4o",
    name="orchestrator",
    instructions="Delegate to specialist agents as needed.",
    tools=[connected_stock.definitions[0], connected_weather.definitions[0]]
)
```

Inspect sub-agent calls via `RunStepConnectedAgentToolCall` in run steps.

#### Semantic Kernel Integration

```python
from semantic_kernel.agents import AzureAIAgent, AzureAIAgentSettings, AzureAIAgentThread

async with AzureAIAgent.create_client(credential=creds) as client:
    agent = AzureAIAgent(client=client, definition=agent_def, plugins=[MyPlugin()])
    thread = AzureAIAgentThread()

    async for response in agent.invoke(messages="What's the special?", thread=thread):
        print(response.content)
        thread = response.thread

    # Streaming
    async for chunk in agent.invoke_stream(messages="Tell me more.", thread=thread):
        print(chunk.content, end="")
```

SK Plugins auto-register as agent tools via `@kernel_function` decorator.

#### AutoGen Integration

```python
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient

model_client = AzureOpenAIChatCompletionClient(
    azure_deployment="gpt-4o",
    azure_endpoint=os.environ["AZURE_OPENAI_API_ENDPOINT"],
    api_key=os.environ["AZURE_OPENAI_KEY"]
)
team = RoundRobinGroupChat(
    [AssistantAgent("searcher", model_client=model_client, tools=[bing_tool]),
     AssistantAgent("writer",  model_client=model_client)],
    termination_condition=TextMentionTermination("DONE") | MaxMessageTermination(10)
)
```

**Note:** Microsoft is consolidating AutoGen and Semantic Kernel into the **Microsoft Agent Framework** (GA Oct–Nov 2025), supporting MCP and Agent-to-Agent (A2A) protocols.

#### Model Router (GA November 2025)

Pass `model="model-router"` to automatically select the optimal LLM per prompt based on complexity, cost, and performance. No code changes when new models arrive.

```python
router_agent = agents_client.create_agent(model="model-router", ...)
```

**Available model families (June 2026):**

| Family | Key Models | Use Case |
|---|---|---|
| GPT-4o | `gpt-4o`, `gpt-4o-mini`, `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano` | General, function calling, streaming |
| Reasoning | `o1`, `o3`, `o3-mini`, `o3-pro` | Deep reasoning, parallel tool calling |
| Deep Research | `o3-deep-research` | Only via DeepResearchTool |
| Phi-4 | `Phi-4 Reasoning Vision 15B` | Multimodal reasoning, charts |
| DeepSeek | `DeepSeek-R1`, `DeepSeek-V3` | Scientific/coding reasoning |
| Anthropic | `claude-haiku-4-5`, `claude-sonnet-4-5`, `claude-opus-4-1` | Via Foundry marketplace |
| GPT-5 | `gpt-5.4-mini` | Classification, extraction, lightweight tools |

#### Streaming Responses

```python
class MyEventHandler(AgentEventHandler[str]):
    def on_message_delta(self, delta: MessageDeltaChunk):
        return delta.text
    def on_run_step(self, step: RunStep):
        return f"[Step {step.type}: {step.status}]"

with agents_client.runs.stream(thread_id=thread.id, agent_id=agent.id,
                                event_handler=MyEventHandler()) as stream:
    for event_type, event_data, func_return in stream:
        print(func_return, end="", flush=True)
```

---

## Part B: External APIs & Frameworks

### B1. Observability & Tracing (External)

| Tool | Package | Self-Host | Multi-Agent Trees | Eval Framework | Best For |
|---|---|---|---|---|---|
| **Langfuse** | `langfuse` | Yes (MIT) | Yes (graph view) | Yes | Data sovereignty, polyglot stacks |
| **LangSmith** | `langsmith` | Enterprise only | Yes (best for LangGraph) | Yes (LLM-as-judge + replay) | LangGraph-heavy teams |
| **Arize Phoenix** | `arize-phoenix` | Yes (ELv2) | Yes (OTel spans) | Yes (ML-grade) | ML-heavy, regulated workloads |
| **W&B Weave** | `weave` | No | Yes (sessions/turns native) | Yes (Scorers + Datasets) | ML+LLM unified, Python-first |
| **Helicone** | `helicone` | Enterprise only | No (session tags only) | No | Cost monitoring, AI gateway |

#### Langfuse

```python
pip install langfuse
```
- Hierarchical span/trace tree for LLM calls, retrieval, tools, and chained steps
- Session-level grouping for multi-turn conversations; token cost per trace
- OTel-native: any OTel-compatible framework can send spans directly
- 50+ framework integrations (LangChain, LlamaIndex, DSPy, etc.)
- Pricing: $0 (50k units/mo) → $29/mo → $199/mo → $2,499/mo (enterprise)
- **Acquired by ClickHouse Inc., January 2026** — product unchanged

#### Arize Phoenix

```python
pip install arize-phoenix openinference-instrumentation-<framework>
```
- OpenInference (OTel-based) telemetry standard
- Pre-built evaluators: faithfulness, relevance, hallucination, toxicity
- ML-heritage: drift detection, embedding analysis, data clustering
- Runs locally in Jupyter notebooks with zero external dependencies
- Self-hosted: free/unlimited; Cloud: $50/mo (Pro)

#### W&B Weave

```python
import weave
weave.init("project-name")

@weave.op()   # zero-friction tracing via decorator
def my_agent_step(query: str) -> str: ...
```
- Agent-native trace structure: sessions, turns, steps, tools, sub-agents as first-class concepts
- **Weave Guardrails:** Built-in safety scorers — toxicity, bias, PII detection, hallucination, coherence, fluency, context relevance
- Evaluation framework: Datasets + Scorers + Evaluations → regression dashboards
- **W&B MCP server:** Coding agents can read production data, run evals, and iterate autonomously
- Pricing: $0 (1 GB/mo ingestion) → ~$60/mo team

#### LangSmith

```python
# LangChain: just set env variable
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY=...
```
- Zero-config for LangChain/LangGraph: automatic instrumentation
- LangGraph: node-by-node state diffs, full execution graph visualization
- LangSmith Engine (2026): AI layer that analyzes traces and suggests fixes
- Production trace replay as regression datasets
- Agent Builder: deploy and run agents directly from LangSmith
- Pricing: $0 (5,000 traces/mo, 14-day retention) → $39/seat/mo
- **Warning:** Heavy LangChain/LangGraph lock-in; depth is significantly reduced for other stacks

#### Helicone

```python
# Zero code — just change base URL + add one header
openai_client = OpenAI(
    base_url="https://oai.helicone.ai/v1",
    default_headers={"Helicone-Auth": f"Bearer {HELICONE_API_KEY}"}
)
```
- Lowest integration friction: one baseURL change, zero instrumentation
- AI Gateway: load balancing across 100+ models, intelligent caching, failover, rate limiting
- Cost monitoring per request, per user, per session
- Reported 20–30% cost reduction via caching on repetitive tool calls
- Pricing: $0 (10k requests/mo, 7-day retention) → $79/mo

---

### B2. Safety & Guardrails (External)

#### Guardrails AI

```bash
pip install guardrails-ai
guardrails hub install hub://guardrails/toxic_language
guardrails hub install hub://guardrails/detect_pii
```

```python
from guardrails import Guard, OnFailAction
from guardrails.hub import ToxicLanguage, DetectPII

guard = Guard().use_many(
    ToxicLanguage(on_fail=OnFailAction.EXCEPTION),
    DetectPII(pii_entities=["EMAIL_ADDRESS", "PHONE_NUMBER"], on_fail=OnFailAction.FIX),
)
result = guard(openai.chat.completions.create, model="gpt-4o", messages=[...])
```

**`on_fail` actions:** `EXCEPTION`, `FIX` (auto-rewrite), `FILTER` (remove), `NOOP`, `REASK` (retry with correction prompt).

**Available validator categories (Guardrails Hub):**

| Category | Examples |
|---|---|
| Content safety | `toxic_language`, `nsfw_text`, `profanity_free` |
| PII / PHI | `detect_pii` (Microsoft Presidio — emails, SSNs, phone, address, credit cards) |
| Security | `secrets_present`, `jailbreak`, `sql_injection_check` |
| Structural | `valid_json`, `valid_python`, `regex_match` |
| Grounding | `provenance_v1` (RAG faithfulness) |
| Bias | `bias_check` (age, gender, ethnicity, religion) |

**Hosted option:** `guardrails start` launches an OpenAI-compatible Flask server at `/v1/chat/completions`.

**Docs:** https://guardrailsai.com

#### NVIDIA NeMo Guardrails

```bash
pip install nemoguardrails   # v0.21.0
```

```python
from nemoguardrails import LLMRails, RailsConfig
config = RailsConfig.from_path("./config")
rails = LLMRails(config)
response = await rails.generate_async(messages=[{"role": "user", "content": user_input}])
```

**Five rail types:**

| Rail | Stage | Purpose |
|---|---|---|
| Input | Pre-LLM | Jailbreak/injection detection, reject/modify |
| Dialog | Mid-conversation | Topic scope, canonical flows via Colang DSL |
| Retrieval | RAG chunk fetch | Filter injected knowledge |
| Execution | Agent tool calls | Gate and validate tool inputs/outputs |
| Output | Post-LLM | Fact-check, sensitive data blocking |

**Colang DSL example:**
```colang
define user ask about competitor
  "Tell me about [competitor]."
define flow
  user ask about competitor
  bot say "I can only discuss our own products."
```

**Agent integration:** Execution rails specifically intercept agent tool calls — define allowed/blocked actions before a tool fires.
**Server mode:** `nemoguardrails server` → OpenAI-compatible HTTP API.

**Docs:** https://github.com/NVIDIA-NeMo/Guardrails

#### LlamaGuard 4 (Meta, April 2025)

**Model:** `meta-llama/Llama-Guard-4-12B` (text + multiple images)
**Install:** `pip install transformers` or `pip install vllm`

```python
# Via transformers
from transformers import AutoProcessor, Llama4ForConditionalGeneration
processor = AutoProcessor.from_pretrained("meta-llama/Llama-Guard-4-12B")
model = Llama4ForConditionalGeneration.from_pretrained("meta-llama/Llama-Guard-4-12B")
```

**Safety categories (S1–S14, MLCommons taxonomy):**
S1 Violent crimes | S2 Non-violent crimes | S3 Sex-related crimes | S4 CSAM | S5 Defamation | S6 Specialized advice | S7 Privacy | S8 Intellectual property | S9 Indiscriminate weapons (CBRN) | S10 Hate speech | S11 Suicide/self-harm | S12 Sexual content | S13 Election misinformation | **S14 Code interpreter abuse**

Output: `safe` or `unsafe` + category code(s). Uses first-token probability for fast binary classification.

**Agent pipeline integration:**
1. Pre-LLM: Pass user message to LlamaGuard; reject if `unsafe`
2. Post-LLM: Pass model response to LlamaGuard; suppress if `unsafe`
3. Tool call safety (S14): Optimized for code interpreter and search tool I/O

**Hosted options:** HuggingFace Inference API, vLLM, NVIDIA Build (build.nvidia.com), Groq, OpenRouter, Together.ai

#### Rebuff (ARCHIVED May 16, 2025)

Do not use in new projects. Was a 4-layer prompt injection detector (heuristics + LLM + vector DB + canary tokens). Use NeMo Guardrails execution rails or Guardrails Hub `jailbreak` validator instead.

---

### B3. Evaluation Frameworks (External)

#### RAGAS

```bash
pip install ragas
```

**Strongest for:** RAG quality + agentic evaluation. 30+ metrics.

**Key metric categories:**

| Category | Metrics | Computation |
|---|---|---|
| RAG Retrieval | Context Precision, Context Recall, Noise Sensitivity | LLM-as-judge |
| RAG Generation | Faithfulness, Response Relevancy, Response Groundedness | LLM-as-judge |
| Answer Quality | Factual Correctness, Answer Accuracy, Semantic Similarity | LLM-as-judge / Embedding |
| **Agent** | **Tool Call Accuracy, Tool Call F1, Agent Goal Accuracy, Topic Adherence** | Deterministic + LLM-as-judge |
| Classic NLP | BLEU, ROUGE, CHRF, Exact Match | Deterministic |

```python
from ragas import evaluate
from ragas.metrics import faithfulness, context_precision, answer_relevancy
results = evaluate(dataset, metrics=[faithfulness, context_precision, answer_relevancy])
```

**Docs:** https://docs.ragas.io

#### DeepEval

```bash
pip install deepeval
```

**Strongest for:** Pytest-style LLM unit tests, 50+ metrics, cloud reporting via Confident AI.

```python
from deepeval import evaluate
from deepeval.test_case import LLMTestCase
from deepeval.metrics import FaithfulnessMetric, GEval

metric = FaithfulnessMetric(threshold=0.7, model="gpt-4o")
test_case = LLMTestCase(input="...", actual_output="...", retrieval_context=["..."])
evaluate([test_case], [metric])
```

**Key metrics:** Faithfulness, Contextual Precision/Recall/Relevancy, G-Eval (custom CoT criteria), Hallucination, Toxicity, Bias, Tool Correctness, Task Completion, Conversational Completeness.

**Computation:** QAG (question-answer generation), DAG (directed acyclic graphs), G-Eval (Chain-of-Thought). Any LLM judge: OpenAI, Azure, Anthropic, Gemini, Ollama via `DeepEvalBaseLLM`.

**Docs:** https://deepeval.com

#### PromptFoo

```bash
npm install -g promptfoo   # primary
pip install promptfoo      # thin wrapper
```

**Strongest for:** Red teaming, regression testing, adversarial probing. 50+ LLM providers.

```yaml
# promptfooconfig.yaml
prompts:
  - "Translate '{{text}}' to French"
providers:
  - openai:gpt-4o
  - anthropic:claude-3-5-sonnet-20241022
tests:
  - vars:
      text: "Hello world"
    assert:
      - type: llm-rubric
        value: "Translation should be accurate French"
      - type: contains
        value: "Bonjour"
```

**50+ red team vulnerability types:** Jailbreaks, indirect prompt injection, PII leakage, SSRF, SQL injection, RAG poisoning, OWASP LLM Top 10, brand safety, compliance violations.

**Docs:** https://www.promptfoo.dev

#### TruLens

```bash
pip install trulens trulens-providers-openai trulens-apps-langchain
```

**Strongest for:** Tracing + RAG eval in one, offline/local evaluation via HuggingFace NLI models.

```python
from trulens.core import TruSession, Feedback
from trulens.providers.openai import OpenAI

provider = OpenAI()
f_groundedness = Feedback(provider.groundedness_measure_with_cot_reasons).on_input_output()

from trulens.apps.langchain import TruChain
tru_chain = TruChain(chain, feedbacks=[f_groundedness])
```

**RAG Triad:** Context Relevance, Groundedness, Answer Relevance.
**Offline capable:** Groundedness via HuggingFace NLI entailment — no external API needed.
**OTel-based tracing:** Decorator `@instrument(span_type=SpanAttributes.SpanType.MCP)` for MCP tool calls.
**Snowflake AI Observability:** Cloud platform backend (acquired by Snowflake, May 2024).

**Docs:** https://www.trulens.org

---

## Part C: Integration Map for MSF Reasoning Agent

The reasoning agent pipeline is: **entry → gate → router → answer**. Here is where each tool fits:

### At the Entry Gate (User Input Received)

| Tool | Action | Why |
|---|---|---|
| `azure-ai-contentsafety` Prompt Shields | `shieldPrompt(userPrompt=input)` | Block jailbreaks, role-play attacks, encoding attacks |
| `LlamaGuard 4` | Classify input S1–S14 | Secondary classifier, especially for specialized advice (S6) and CSAM (S4) |
| Guardrails AI `jailbreak` validator | Guard wrapping input processing | Third-layer defense using pattern-based detection |
| `azure-ai-evaluation` `IntentResolutionEvaluator` | Offline: evaluate if gate correctly classifies intent | CI/CD regression testing |

### At the Router (Model/Path Selection)

| Tool | Action | Why |
|---|---|---|
| Azure AI Model Router (`model="model-router"`) | Auto-select model per complexity | Cost-optimized routing without manual complexity detection |
| `AIInferenceInstrumentor` + Azure Monitor | Trace every model call with token counts | Identify which model branch is most expensive |
| W&B Weave `@weave.op()` | Trace router decision logic | Captures routing inputs/outputs for offline analysis |

### At the RAG/Retrieval Step

| Tool | Action | Why |
|---|---|---|
| Azure AI Search Agentic Retrieval | LLM-planned multi-subquery decomposition | Best accuracy for complex multi-hop questions |
| Hybrid search (`queryType=semantic`, `vectorQueries`) | BM25 + vector + L2 semantic reranking | Outperforms pure vector by 10–20% on relevance |
| `shieldPrompt(documents=chunks)` | Scan retrieved chunks for indirect injection | RAG poisoning defense |
| `detectGroundedness` | Post-LLM factual grounding check | Catch hallucinations before returning answer |

### At the Answer Step (Post-LLM)

| Tool | Action | Why |
|---|---|---|
| `azure-ai-contentsafety` `analyze_text` | Harm categories on LLM output | Block hate/violence/sexual/self-harm in responses |
| `detectProtectedMaterial` | Copyright check on LLM output | Prevent IP violations in generated content |
| Task Adherence API | Verify tool calls matched user intent | Prevent misaligned tool invocations in multi-step flows |
| RAGAS `Faithfulness` + `AgentGoalAccuracy` | Offline eval dataset | Measure end-to-end answer quality per session |

### For Evaluation & Observability (Offline / CI)

| Tool | Use |
|---|---|
| `azure-ai-evaluation` `ToolCallAccuracyEvaluator` + `TaskAdherenceEvaluator` | Unit-test every agent tool-calling scenario |
| AI Red Teaming Agent (PyRIT) | Monthly red-team runs: jailbreak, XPIA, prohibited actions, sensitive data leakage |
| Langfuse (self-hosted) or Arize Phoenix | Production trace storage with eval annotation for non-Azure stacks |
| RAGAS | Golden dataset evaluation — context precision, faithfulness, agent goal accuracy |
| DeepEval | Pytest integration for per-PR regression gates |
| PromptFoo | Pre-deployment adversarial probing (50+ vulnerability types) |

---

### B4. Agent Memory Systems (External)

| Tool | Package | Memory Model | Self-Host | Best For |
|---|---|---|---|---|
| **Mem0** | `mem0ai` | Multi-store (vector + graph + KV) | Yes (Apache 2.0) | Broad ecosystem, AWS Strands native |
| **Zep** | `zep-cloud` | Temporal knowledge graph (Graphiti) | Yes (Docker) | Evolving facts, entity relationships |
| **Letta** (MemGPT) | `letta-client` | OS-inspired 3-tier (core/recall/archival) | Yes (Apache 2.0) | Agent-controlled memory, full control |

#### Mem0

```bash
pip install mem0ai
```

```python
from mem0 import MemoryClient

client = MemoryClient(api_key="your-key")
client.add("User prefers concise answers in Python", user_id="user123")
results = client.search("programming preferences", user_id="user123")
```

**Memory types:** Semantic/factual (all tiers), graph/relational (Pro only, Neo4j/Kuzu), temporal (Feb 2026+), key-value.

**Memory scopes:** `user_id`, `agent_id`, `run_id`/`session_id`, `app_id`/`org_id`

**20 vector store backends:** Qdrant, Chroma, Weaviate, Pinecone, Azure AI Search, PGVector, Redis, FAISS, S3 Vectors, MongoDB, etc.

**13 framework integrations:** LangChain, LangGraph, LlamaIndex, CrewAI, AutoGen, OpenAI Agents SDK, Google ADK, Mastra (TypeScript)

**MCP server:** `mem0-mcp-server` — lets Claude/LLMs self-manage memory

**2026 benchmarks (self-reported):**
| Benchmark | Score | Tokens/Query |
|---|---|---|
| LoCoMo | 92.5% | 6,956 |
| LongMemEval | 94.4% | 6,787 |
vs. full-context baselines requiring ~26,000 tokens/query → **73% token reduction**

**Pricing:** Free (10K memories, 1K retrievals/mo) → $19/mo → $79/mo → $249/mo (graph memory)

**OSS self-hosted:** Full Apache 2.0, all features, no gating. Default: Qdrant + `text-embedding-3-small` + SQLite history.

#### Zep

```bash
pip install zep-cloud
```

```python
from zep_cloud.client import Zep

client = Zep(api_key=os.getenv("ZEP_API_KEY"))
client.memory.add_session(session_id="sess_123", user_id="user_abc")
client.memory.add(session_id="sess_123", messages=[...])
memory = client.memory.get(session_id="sess_123")
```

**Core engine:** Graphiti — a **temporal knowledge graph** where outdated facts are automatically invalidated (not overwritten). Key differentiator: tracks fact evolution over time.

**Retrieval:** Graph traversal + vector search + BM25 hybrid. Sub-200ms P95 latency.

**LangChain:** `ZepChatMessageHistory`, `ZepVectorStore` from `zep_cloud.langchain`

**Graphiti MCP Server:** Gives Claude Desktop, Cursor, VS Code Copilot persistent graph memory.

**2026 benchmarks:** LongMemEval temporal retrieval 63.8% vs. Mem0's 49% — strongest at tracking changing facts.

**Pricing:** Free (1K credits/mo) → $125/mo (Flex) → $375/mo (Flex Plus) → Enterprise

**Note:** Zep Community Edition **deprecated April 2025**. BYOC/BYOM/HIPAA BAA on Enterprise only.

#### Letta (MemGPT Successor)

```bash
pip install letta-client   # cloud SDK
pip install letta           # full OSS framework (Apache 2.0, no feature gating)
```

```python
from letta_client import Letta

client = Letta(api_key=os.getenv("LETTA_API_KEY"))
agent = client.agents.create(
    model="openai/gpt-4.1",
    memory_blocks=[
        {"label": "human", "value": "Name: Alice. Prefers concise answers."},
        {"label": "persona", "value": "I am a helpful research assistant."}
    ]
)
response = client.agents.messages.create(agent_id=agent.id, input="What do you know about me?")
```

**3-tier OS-inspired model:**
- **Core memory** (always in LLM context, like RAM): `human` + `persona` blocks; agent calls `memory_replace` to update
- **Recall memory** (searchable conversation history): agent calls `conversation_search`
- **Archival memory** (long-term semantic store): agent calls `archival_memory_search` / `archival_memory_insert`

**Key distinction:** The agent itself decides when to read/write across tiers via tool calls — not the framework. This is "LLM-as-OS" rather than passive injection.

**2026 benchmarks:** LoCoMo ~83% (highest verified score for open-source, per independent analysis). Letta Code: #1 model-agnostic OSS agent on Terminal-Bench (Apr 2026).

**Pricing:** Free (limited) → $20/mo (Pro) → Enterprise. **Self-hosted OSS: completely free, all features.**

---

### B5. Reasoning & Prompt Optimization (External)

#### DSPy (Stanford, `pip install dspy`)

The most production-relevant reasoning enhancement tool. Shifts from manual prompt engineering to **programmatic compilation** — define typed signatures, let DSPy auto-optimize prompts against a metric.

```python
import dspy

# Declare typed I/O (no manual prompts)
class RAGModule(dspy.Module):
    def __init__(self):
        self.retrieve = dspy.Retrieve(k=3)
        self.generate = dspy.ChainOfThought("context, question -> answer")
    
    def forward(self, question):
        context = self.retrieve(question).passages
        return self.generate(context=context, question=question)

# Tool-using agent
react_agent = dspy.ReAct("question -> answer", tools=[calculator, search_web])

# Auto-optimize: find best instructions + few-shot examples
optimizer = dspy.BootstrapFewShot(metric=my_accuracy_metric)
compiled = optimizer.compile(RAGModule(), trainset=examples)
```

**Optimizers:** `GEPA` (reflective prompt evolution — Shopify reports 75x cost reduction), `MIPROv2`, `BootstrapFewShot`, `BetterTogether`.

**Agent modules:** `dspy.Predict`, `dspy.ChainOfThought`, `dspy.ReAct`, `dspy.ReActV2` (parallel + multi-turn tool calls), `dspy.ProgramOfThought`, `dspy.BestOfN`, `dspy.Refine`.

**Production adoption:** 160K+ monthly downloads; used by Shopify, Databricks, Dropbox, AWS, JetBlue, Replit.

**Docs:** https://dspy.ai

#### Tree of Thoughts

A prompting strategy (not a dedicated production library) that branches into multiple parallel thought sequences, supporting backtracking and lookahead before committing to an answer path. Best for planning problems, constraint satisfaction, and multi-step math where single-chain reasoning reliably fails.

**In practice (2026):** Use `dspy.BestOfN` or `dspy.Refine` for production ToT-like behavior — maintained, integrated with DSPy's optimizer stack, and pairs with evaluation metrics automatically.

---

### B6. Structured Output (External)

| Tool | Package | Approach | Provider Support | Schema Guarantee |
|---|---|---|---|---|
| **Instructor** | `instructor` | Post-gen + Pydantic validation + retry | Any (OpenAI, Anthropic, Gemini, Ollama, 15+) | No (retries) |
| **Outlines** | `outlines` | Pre-gen FSM — masks invalid tokens | Local models only (vLLM, TGI, Transformers) | Yes (100%) |
| **Guidance** | `guidance` | Pre-gen + conditional branching in gen loop | Local models only | Yes (100%) |

#### Instructor

```python
import instructor
from openai import OpenAI
from pydantic import BaseModel
from typing import Literal

class Sentiment(BaseModel):
    label: Literal["positive", "negative", "neutral"]
    confidence: float

client = instructor.from_openai(OpenAI())
result = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Analyze: This product is amazing!"}],
    response_model=Sentiment,
    max_retries=3,
)
# result.label → "positive", result.confidence → 0.97
```

12.3K GitHub stars. Official SDKs in Python, TypeScript, Go, Ruby. Best for cloud API-based extraction between agent steps.

#### Outlines

```python
import outlines
model = outlines.from_transformers(llm, tokenizer)
result = model("Analyze sentiment: This is terrible!", Sentiment)
# Guaranteed valid schema on first pass — zero retries, zero wasted API calls
```

100% schema compliance via FSM — compiled once, microsecond overhead per token. Backend for vLLM and HuggingFace TGI. **Local inference only.** As of May 2025, powers OpenAI's own structured outputs feature.

#### Guidance (Microsoft)

```python
from guidance import models, select, guidance

@guidance
def route_and_extract(lm, text):
    lm += f"Input: {text}\n"
    lm += f"Type: {select(['bug', 'feature'], name='type')}\n"
    if lm["type"] == "bug":
        lm += gen_json(name="result", schema=BugReport)
    return lm
```

**Unique:** Conditional schemas — different output structure based on intermediate model decisions. ~50µs CPU overhead per token. The underlying `llguidance` Rust library has been adopted by llama.cpp, vLLM, SGLang, mistral.rs, ONNX Runtime GenAI. **Local inference only.**

---

### B7. Vector Databases (External)

| DB | Deployment | Hybrid Search | Latency (10M vecs) | Best For |
|---|---|---|---|---|
| **Qdrant** | OSS + Cloud | Yes (vector + BM25) | ~12ms P99 | High-perf, self-hosted, complex filters |
| **Weaviate** | OSS + Cloud | Yes (best native) | ~16ms P99 | Best out-of-box hybrid, multi-tenant |
| **Pinecone** | Managed only | Yes (dense + sparse) | ~10–15ms P99 | Zero-ops, multi-tenant namespaces |
| **Chroma** | OSS + in-process | No (vector only) | ~30ms P99 | Dev/prototyping, LangChain default |
| **pgvector** | Self-hosted (Postgres) | Partial | ~25–40ms P99 | Postgres-native, easy ops |

**Scale guide:**
- Under 10M vectors: Chroma (dev) or pgvector (Postgres-native prod)
- 10M–1B: Pinecone (managed), Qdrant (self-hosted perf), or Weaviate (hybrid search)
- Above 1B: Vespa or Milvus distributed

**For MSF Reasoning Agent specifically:** Qdrant is already supported as a Mem0 backend (one of 20 backends). Azure AI Search is also a Mem0 backend — keeps everything in the Azure ecosystem if preferred.

---

## Sources

### Azure AI Foundry (Official Microsoft Docs)
1. [Local Evaluation SDK](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/develop/evaluate-sdk)
2. [Agent Evaluators Reference](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/agent-evaluators)
3. [Custom Evaluators](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/custom-evaluators)
4. [Cloud Evaluation SDK](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/develop/cloud-evaluation)
5. [AI Red Teaming Agent Concepts](https://learn.microsoft.com/en-us/azure/foundry/concepts/ai-red-teaming-agent)
6. [Set Up Tracing for AI Agents in Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/trace-agent-setup)
7. [Configure Tracing for Agent Frameworks](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/trace-agent-framework)
8. [Monitor AI Agents with Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/agents-view)
9. [Azure AI Content Safety Overview](https://learn.microsoft.com/en-us/azure/ai-services/content-safety/overview)
10. [Prompt Shields Concepts](https://learn.microsoft.com/en-us/azure/ai-services/content-safety/concepts/jailbreak-detection)
11. [Groundedness Detection](https://learn.microsoft.com/en-us/azure/ai-services/content-safety/concepts/groundedness)
12. [Agentic Retrieval Overview](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-overview)
13. [File Search Tool for Foundry Agents](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/file-search)
14. [Hybrid Search Overview](https://learn.microsoft.com/en-us/azure/search/hybrid-search-overview)
15. [Integrated Vectorization Overview](https://learn.microsoft.com/en-us/azure/search/vector-search-integrated-vectorization)
16. [Foundry Agent Service Overview](https://learn.microsoft.com/en-us/azure/foundry/agents/overview)
17. [SK AzureAIAgent](https://learn.microsoft.com/en-us/semantic-kernel/frameworks/agent/agent-types/azure-ai-agent)
18. [Foundry SDK Overview](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/sdk-overview)

### GitHub Samples
19. [azure-ai-projects Python samples](https://github.com/Azure/azure-sdk-for-python/tree/main/sdk/ai/azure-ai-projects/samples)
20. [azure-ai-agents README](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/ai/azure-ai-agents/README.md)
21. [Azure Search Agentic Retrieval Python samples](https://github.com/Azure-Samples/azure-search-python-samples/tree/main/Quickstart-Agentic-Retrieval)
22. [Microsoft OpenTelemetry distro LangChain sample](https://github.com/microsoft/opentelemetry-distro-python/tree/main/samples/langchain)

### External Tools
23. [RAGAS Documentation](https://docs.ragas.io)
24. [DeepEval Documentation](https://deepeval.com)
25. [PromptFoo Documentation](https://www.promptfoo.dev)
26. [TruLens Documentation](https://www.trulens.org)
27. [Guardrails AI Hub](https://guardrailsai.com)
28. [NeMo Guardrails GitHub](https://github.com/NVIDIA-NeMo/Guardrails)
29. [LlamaGuard 4 HuggingFace](https://huggingface.co/meta-llama/Llama-Guard-4-12B)
30. [Langfuse Documentation](https://langfuse.com/docs)
31. [Arize Phoenix](https://arize.com/phoenix/)
32. [W&B Weave](https://wandb.ai/site/weave/)
33. [LangSmith](https://smith.langchain.com)
34. [Helicone Changelog](https://www.helicone.ai/changelog)
35. [LLM Eval Frameworks Compared — Atlan](https://atlan.com/know/llm-evaluation-frameworks-compared/)
36. [Top AI Guardrails Tools 2026 — FutureAGI](https://futureagi.com/blog/top-5-ai-guardrailing-tools-2025/)
37. [Agent Observability Comparison 2026 — Latitude](https://latitude.so/blog/best-ai-agent-observability-tools-2026-comparison)
38. [LangSmith 2026 — Medium](https://medium.com/@sehaj23chawla/langsmith-and-langgraph-in-2026-how-langchains-agent-stack-quietly-became-the-default-f1609af5d658)

---

*Methodology: 8 parallel research agents, 40+ queries, 30+ sources scraped in full. Covers Azure AI Foundry SDK state as of June 2026 (GA: evaluations, monitoring, tracing; Preview: hosted agents, agentic retrieval MCP, task adherence API).*
