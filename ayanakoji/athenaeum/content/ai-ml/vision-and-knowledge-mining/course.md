---
kind: course
id: ai-c03
vertical: ai-ml
course_id: ai-c03
title: Computer Vision & Knowledge Mining
level: advanced
grounded_on: "AI-102 skills outline (2025-12-23), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/ai-102
synthetic: true
prereqs: [ai-c01, ai-c02]
objectives: []
---

# Computer Vision & Knowledge Mining

Most enterprise content is not neatly typed into a database. It lives in scanned invoices, warehouse photos, marketing video, archived PDFs, and shelves of product imagery — pixels and bytes that no SQL query can reach. This course teaches you to turn that unstructured visual and textual sprawl into something a system can read, classify, and search. You will analyze images and video with Azure AI Vision, train models that recognize the things *your* business cares about, and stand up an Azure AI Search index that lets people find an answer buried across thousands of documents in a few hundred milliseconds.

## Who this is for

You are a developer or applied-AI engineer who has already built generative and language solutions on Azure and now needs to handle pixels and large content corpora. The work assumes you are comfortable with Python, REST, async patterns, and authenticating to Azure with `DefaultAzureCredential`. It is the advanced course in the AI & Machine Learning Engineering vertical and builds directly on **Generative AI Solutions with Azure OpenAI** (ai-c01) and **Language & Document Intelligence** (ai-c02); the retrieval skills you learned there meet their natural home here, where the index doing the retrieving is the thing you build.

## What you'll be able to do

- Select and call the right Azure AI Vision features — captions, tags, object detection, and OCR — for a given image-processing requirement.
- Train, evaluate, and consume custom image classification and object-detection models on your own labeled data.
- Extract structured insights from video and live streams using Video Indexer and spatial analysis.
- Provision Azure AI Search and define an index, a skillset, a data source, and an indexer.
- Implement semantic ranking and vector search so users get relevant answers, not just keyword matches.
- Reason about cost, accuracy, and operational trade-offs across vision and search services.

## Module path

This course is four sequential modules; each builds on the last.

1. **Analyzing images and extracting text** — Use prebuilt Vision features and OCR to caption, tag, locate objects, and read printed and handwritten text from images.
2. **Custom vision models** — Decide between classification and object detection, label data, train, evaluate the metrics that matter, and publish a model you can call.
3. **Extracting insights from video** — Pull transcripts, faces, topics, and scene data from video with Video Indexer, and detect people and movement with spatial analysis.
4. **Knowledge mining with Azure AI Search** — Compose data sources, skillsets, indexers, and indexes, then layer semantic and vector search to make a corpus genuinely findable.

## Prerequisites

You should complete **Generative AI Solutions with Azure OpenAI** (ai-c01) and **Language & Document Intelligence** (ai-c02) first, or have equivalent experience. From those you carry forward two things this course leans on hard: comfort calling Azure AI services with key-based and Microsoft Entra authentication, and a working mental model of embeddings and retrieval-augmented generation. You also need an Azure subscription with permission to create AI Vision, Video Indexer, and AI Search resources, plus a working Python 3.9+ environment.

## How this fits the bigger picture

Vision and knowledge mining are the two halves of making *all* of an organization's content usable by AI, not just the slice that happens to be structured text. Vision turns images and video into descriptions, labels, and coordinates; knowledge mining turns a heap of documents into a queryable index with relevance ranking. Together they are also the backbone of production RAG: the AI Search index you build in the final module is the same component a grounded chat assistant queries to find its context. By the end you will be able to design the retrieval and enrichment layer that the generative work in ai-c01 only consumed — closing the loop on a full enterprise AI solution where a model can both *see* and *find*.
