---
kind: module
id: ai-c03-m04
vertical: ai-ml
course_id: ai-c03
title: Knowledge mining with Azure AI Search
level: advanced
grounded_on: "AI-102 skills outline (2025-12-23), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/ai-102
synthetic: true
order: 4
prereqs: [ai-c03-m02]
objectives:
  - Provision Azure AI Search and define an index, a skillset, a data source, and an indexer
  - Run an indexer that enriches and ingests content into a searchable index
  - Implement semantic ranking and vector search and write queries with filters and sorting
---

# Knowledge mining with Azure AI Search

By now Driftwood Outfitters has captions and tags from images, transcripts from video reviews, and a warehouse full of PDFs — supplier contracts, product manuals, safety data sheets. Each piece is individually understood, and yet a support agent still cannot answer "which manuals mention replacing the Summit 45 rain fly?" without opening files one by one. Understanding content is not the same as making it *findable*. Knowledge mining is the discipline of taking a heap of heterogeneous content, enriching it, and loading it into a structure that returns the right answer to a natural query in milliseconds. This is also the component that quietly powers production RAG: the grounded chat assistant from the first course in this vertical doesn't reason its way to your data — it queries an index exactly like the one you're about to build.

## Learning objectives

By the end of this module you will be able to:

- Provision an Azure AI Search resource and define the four core objects: index, data source, skillset, and indexer.
- Use a skillset to enrich documents with AI during ingestion.
- Run an indexer to pull, enrich, and load content into an index.
- Implement semantic ranking and vector search, and write queries using filters, sorting, and wildcards.

## Concepts

### The four objects that make a search solution

Azure AI Search is built from four cooperating objects, and understanding their division of labor is the whole game. A **data source** tells the service where your content lives — a Blob Storage container, a Cosmos DB collection, a SQL table. An **index** is the target schema: the fields your documents will be stored and queried against, each with attributes declaring whether it is searchable, filterable, sortable, facetable, or retrievable. A **skillset** is an optional AI enrichment pipeline that runs *during* ingestion — calling OCR, key-phrase extraction, entity recognition, or your own custom skill to add fields the raw document didn't have. An **indexer** is the engine that ties them together: on a schedule or on demand, it crawls the data source, runs documents through the skillset, maps the results to index fields, and loads them.

The mental model: the data source is the *where*, the index is the *shape*, the skillset is the *enrichment*, and the indexer is the *process* that moves content from one to the other while enriching it. You can also push documents directly into an index via the API without an indexer, which you'd do when your application already has the data in hand rather than crawling a store.

### Enrichment turns documents into fields

The power of a skillset is that it manufactures structure that wasn't in the source. A scanned PDF contract is, to a raw crawler, a blob of bytes. Run it through a skillset with an OCR skill and a key-phrase skill and the same document arrives in the index with extracted text, key phrases, and detected entities as real, queryable fields. This is where the earlier modules connect: an image caption, a custom-vision tag, or a Video Indexer transcript can all become fields in a search index, so a single text query spans documents, images, and video. Enriched values can also be persisted to a knowledge store for reuse beyond search. The discipline is to enrich only what you'll query — every skill adds ingestion cost and time.

### Keyword, semantic, and vector search

Classic full-text search matches *terms*: a query for "rain fly replacement" finds documents containing those words, ranked by a keyword-scoring algorithm. It's fast and precise when the user's words match the document's words — and brittle when they don't. **Semantic ranking** improves this by applying a language model to re-rank the top keyword results by meaning and can surface concise captions and answers, so "how do I swap the tent's waterproof cover?" can rank a document that says "rain fly" highly even without exact word overlap. **Vector search** goes further: you store an embedding (a numeric vector) for each chunk of content and query by vector similarity, finding semantically near matches independent of wording, which is the backbone of RAG. These aren't mutually exclusive — **hybrid search** runs keyword and vector queries together and fuses the rankings, typically giving the best results because it combines exact-term precision with semantic recall. You generate embeddings (for example with an Azure OpenAI embedding model) and store them in a vector field; the index declares that field's dimensions and the similarity metric. Treat exact dimension and configuration details as things to confirm in the docs for your model.

## Walkthrough: indexing Driftwood's manual library

You'll define an index for Driftwood's PDF manuals with a searchable content field and a filterable product field, then query it. This uses the `azure-search-documents` Python SDK with `DefaultAzureCredential`, the right pattern for production. (Defining the data source, skillset, and indexer follows the same client pattern; here we focus on the index and a query to keep the example runnable end to end.)

```python
import os
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex, SearchField, SearchFieldDataType,
    SimpleField, SearchableField,
)

endpoint = os.environ["SEARCH_ENDPOINT"]
credential = DefaultAzureCredential()

index = SearchIndex(
    name="driftwood-manuals",
    fields=[
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SimpleField(name="product", type=SearchFieldDataType.String,
                    filterable=True, facetable=True),
    ],
)
SearchIndexClient(endpoint, credential).create_or_update_index(index)

# Query: free text on content, filtered to one product, ordered by relevance.
search = SearchClient(endpoint, "driftwood-manuals", credential)
results = search.search(
    search_text="replace rain fly",
    filter="product eq 'Summit 45'",
    select=["id", "content", "product"],
    top=5,
)
for r in results:
    print(f"{r['product']} (score {r['@search.score']:.2f}): "
          f"{r['content'][:80]}...")
```

The field attributes are doing quiet, important work. `content` is `SearchableField`, so full-text search runs against it; `product` is a `SimpleField` marked `filterable` and `facetable`, so you can narrow results with `filter="product eq 'Summit 45'"` and offer it as a facet — but it is *not* searchable, because you'd never run free-text relevance scoring on a SKU label. Getting attributes right at design time matters: you can't make a field filterable after the fact without rebuilding the index. The `@search.score` is the relevance the engine assigned. To upgrade this to semantic or vector search you'd add a semantic configuration or a vector field to the index and pass the corresponding query options.

## Common pitfalls

- **Wrong field attributes at design time.** Whether a field is searchable, filterable, sortable, or facetable is largely fixed at index creation. Changing it usually means rebuilding the index and re-ingesting. Model your query patterns *before* defining the schema.
- **Enriching everything.** Every skill in a skillset adds cost and indexing latency. Enrich only the fields your queries actually use; OCR on documents that are already digital text is wasted work.
- **Expecting keyword search to understand meaning.** Plain full-text matches terms, not intent. If users phrase things differently from your documents, add semantic ranking or vector/hybrid search rather than blaming the engine.
- **Storing vectors without hybrid retrieval.** Pure vector search can miss exact-term matches (part numbers, SKUs) that users type verbatim. Combine keyword and vector into hybrid search for the best of both.
- **Ignoring indexer scheduling and failures.** An indexer runs on a schedule and can partially fail on malformed documents. Monitor its execution history and configure error handling, or your index silently drifts out of date.

## Knowledge check

1. A support team complains that searching "waterproof cover swap" returns nothing, even though a manual clearly explains replacing the rain fly. The index uses plain keyword search. What should you add, and why does it help?
2. After launch, the product manager asks to let users filter results by warranty length, a field you stored as searchable-only. Why can't you just flip a switch, and what does it cost you?
3. Which of the four Search objects is responsible for running OCR on a scanned PDF during ingestion, and where do the extracted results end up?

<details>
<summary>Answers</summary>

1. Semantic ranking or vector/hybrid search — keyword search matches terms, and "waterproof cover" never appears in a document that says "rain fly"; semantic/vector retrieval matches by meaning. — Intent-based retrieval bridges vocabulary gaps.
2. Field attributes like filterable are essentially fixed at index creation; making the field filterable requires defining a new/rebuilt index and re-ingesting all documents. — Schema attributes aren't mutable in place.
3. The skillset (via an OCR skill) runs during ingestion; the indexer maps its output into fields of the index. — Skillset enriches, indexer loads.

</details>

## Summary

Knowledge mining is what makes understood content actually findable. Azure AI Search composes four objects — a data source for *where*, an index for *shape*, a skillset for *enrichment*, and an indexer for the *process* — and the enrichment step is where the captions, tags, and transcripts from earlier modules become queryable fields. Choose retrieval to fit the question: keyword for exact terms, semantic ranking and vector search for meaning, and hybrid when you want both, which is usually. Get field attributes right before you build, because they're hard to change after. With this, you've closed the loop on the vertical: you can now build the very retrieval layer that grounds a generative AI assistant in your own enterprise content.

## Further learning

- [What is Azure AI Search?](https://learn.microsoft.com/en-us/azure/search/search-what-is-azure-search)
- [AI enrichment in Azure AI Search](https://learn.microsoft.com/en-us/azure/search/cognitive-search-concept-intro)
- [Semantic ranking in Azure AI Search](https://learn.microsoft.com/en-us/azure/search/semantic-search-overview)
- [Vector search in Azure AI Search](https://learn.microsoft.com/en-us/azure/search/vector-search-overview)
