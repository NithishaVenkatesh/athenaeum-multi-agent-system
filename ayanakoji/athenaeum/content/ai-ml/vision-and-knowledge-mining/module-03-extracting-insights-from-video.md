---
kind: module
id: ai-c03-m03
vertical: ai-ml
course_id: ai-c03
title: Extracting insights from video
level: advanced
grounded_on: "AI-102 skills outline (2025-12-23), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/ai-102
synthetic: true
order: 3
prereqs: [ai-c03-m01]
objectives:
  - Extract insights from recorded video using Azure AI Video Indexer
  - Detect the presence and movement of people in video using spatial analysis
  - Choose between Video Indexer and spatial analysis for a given video scenario
---

# Extracting insights from video

Driftwood Outfitters runs a YouTube channel of gear-review videos and operates a fictional flagship store wired with ceiling cameras. Both produce video, and video is the most opaque content type there is: a one-hour review is 60 minutes of pixels with no transcript, no chapter markers, and no way to jump to "the part about the Summit 45's rain fly." The store's camera feed, meanwhile, holds answers to operational questions — how many people entered, where they lingered — locked inside footage nobody has time to watch. A single image API call cannot solve this, because the signal in video is *temporal*: it's about what happens, when, and in what order. This module covers the two Azure services that turn video into structured, time-stamped insight, and the very different jobs each is built for.

## Learning objectives

By the end of this module you will be able to:

- Upload and index recorded video with Azure AI Video Indexer and retrieve its insights.
- Interpret the time-coded transcript, topics, faces, and labels Video Indexer produces.
- Explain what Azure AI Vision spatial analysis detects and how it differs from content indexing.
- Choose the right service for a content-discovery scenario versus an operational-presence scenario.

## Concepts

### What Video Indexer extracts, and why it's time-coded

Azure AI Video Indexer runs a recorded video through a battery of AI models and returns a rich, time-coded JSON document of insights. It transcribes speech to a timestamped transcript, performs OCR on text that appears on screen, detects and groups faces, identifies topics and keywords, recognizes labels (objects and scenes), splits the video into shots and scenes, and can flag content moderation concerns. The unifying property is that *every insight carries a time range*. The transcript isn't just words; it's words mapped to the second they were spoken. The topic "rain fly" isn't just present; it's present from 12:30 to 14:05.

That time-coding is what makes the output useful rather than merely interesting. Because each insight is anchored to a moment, you can build deep links that jump a viewer straight to the relevant scene, generate chapter markers automatically, or — crucially for the next module — feed the transcript into a search index so a text query over your video library returns *the exact clip*. Video Indexer turns a wall of footage into something addressable.

### The asynchronous reality of video

Video is large and processing is not instant, so Video Indexer is fundamentally asynchronous. You upload a video (or point the service at a URL), the service returns a video ID, and indexing proceeds in the background — for long videos this can take a while, often on the order of the video's own duration or more. Your code uploads, then polls for processing state, and only retrieves insights once the state reports completion. Designing for this means never blocking a user request on indexing; you kick off the job, store the ID, and surface results when they're ready, typically via a callback URL the service can notify or a polling worker. Authentication uses a short-lived access token you request for your account, which scopes what the caller can do and expires, so you fetch a fresh token rather than caching one indefinitely.

### Spatial analysis answers a different question

It is tempting to assume one "video AI" service does everything, but Video Indexer and spatial analysis solve opposite problems. Video Indexer is about *content discovery*: what is said, shown, and meant in recorded media. **Azure AI Vision spatial analysis** is about *operational presence*: it processes a camera stream to detect the presence and movement of people — counting how many cross a line, how many are in a zone, or how long they dwell — without identifying who they are. It's built for live or near-live operational scenarios (footfall, queue length, occupancy) on edge-deployed camera feeds, and it emits events rather than a searchable transcript.

So the choice is rarely ambiguous once you frame the question. "Let users find the moment a product is discussed" is a Video Indexer job. "Count how many people entered the store and where they lingered" is a spatial analysis job. Using Video Indexer to count store visitors would be slow, expensive, and miss the point; using spatial analysis to make a review video searchable is simply the wrong tool. Note that people-counting features carry real privacy and Responsible AI obligations — signage, consent, and a Limited Access registration process for some capabilities — which you should confirm in the current docs before deploying.

## Walkthrough: making the Driftwood review library searchable

Marketing wants every gear-review video to be searchable down to the topic. You'll upload a review to Video Indexer, poll until it's done, and pull the transcript and topics. Video Indexer's REST API is the portable surface, so you'll call it with `requests` using an access token your backend has already obtained.

```python
import os
import time
import requests

ACCOUNT_ID = os.environ["VI_ACCOUNT_ID"]
LOCATION = os.environ["VI_LOCATION"]           # e.g. "trial" or an Azure region
ACCESS_TOKEN = os.environ["VI_ACCESS_TOKEN"]   # short-lived, fetched separately
BASE = f"https://api.videoindexer.ai/{LOCATION}/Accounts/{ACCOUNT_ID}"

# 1. Upload by URL and get a video ID.
upload = requests.post(
    f"{BASE}/Videos",
    params={
        "accessToken": ACCESS_TOKEN,
        "name": "summit-45-review",
        "videoUrl": os.environ["REVIEW_VIDEO_URL"],
    },
)
upload.raise_for_status()
video_id = upload.json()["id"]

# 2. Poll until processing completes.
while True:
    index = requests.get(
        f"{BASE}/Videos/{video_id}/Index",
        params={"accessToken": ACCESS_TOKEN},
    ).json()
    state = index["state"]
    if state in ("Processed", "Failed"):
        break
    time.sleep(30)  # don't hammer the API; video takes time

# 3. Pull time-coded insights.
if state == "Processed":
    insights = index["videos"][0]["insights"]
    for topic in insights.get("topics", []):
        for inst in topic["instances"]:
            print(f"{topic['name']}: {inst['start']} – {inst['end']}")
```

The shape of this code *is* the lesson: upload returns immediately with an ID, you poll on a sensible interval rather than blocking, and only after `Processed` do you read insights. Each topic comes with `instances` carrying `start` and `end` timestamps — those are what you'd turn into deep links so a search result jumps the viewer to 12:30 where the rain fly is discussed. In the next module, you'd push that same transcript into an Azure AI Search index to make the entire library queryable as text.

## Common pitfalls

- **Blocking a user request on indexing.** Video processing is asynchronous and can take as long as the video itself. Kick off the job, store the ID, and return results later via callback or a polling worker — never make a user wait inline.
- **Caching the access token forever.** Video Indexer access tokens are short-lived by design. Fetch a fresh token when needed; a cached, expired token produces confusing 401s.
- **Confusing the two services.** Video Indexer makes recorded content discoverable; spatial analysis counts and tracks people in a live feed. Reaching for the wrong one yields a working-but-pointless integration.
- **Ignoring privacy and Limited Access obligations.** People-presence and face-related features carry Responsible AI requirements, including registration for some capabilities and disclosure to people being recorded. Treat compliance as a design input, not an afterthought; verify current requirements in the docs.
- **Assuming insights are perfect.** Transcripts and topics are model output. For high-stakes use (legal, accessibility compliance) review confidence and allow correction rather than treating insights as ground truth.

## Knowledge check

1. Driftwood wants viewers to click a search result and jump straight to the moment a product is discussed in a review video. Which service produces what you need, and which property of its output makes the deep link possible?
2. The store operations team wants a daily count of how many people entered and which aisle they dwelled in. Which service fits, and why is the *other* one a poor choice here?
3. Your upload call returns instantly with an ID, but a teammate's code reads `insights` immediately afterward and gets nothing useful. What's wrong with their approach?

<details>
<summary>Answers</summary>

1. Azure AI Video Indexer — its insights are time-coded, so each topic instance carries start/end timestamps you can turn into a deep link. — Time anchoring is what makes content addressable.
2. Azure AI Vision spatial analysis — it detects presence and movement of people in a feed; Video Indexer is built for content discovery and would be slow, costly, and not designed for live people-counting. — Operational presence vs. content discovery.
3. Indexing is asynchronous; insights aren't ready the instant upload returns. They must poll the index state until it reports `Processed` before reading insights. — Video processing takes time and returns an ID first.

</details>

## Summary

Video carries meaning in time, so the tools that understand it return time-coded results. Azure AI Video Indexer transcribes, tags, and topic-maps recorded media into addressable insights — the basis for chapters, deep links, and searchable libraries — and it works asynchronously, so you upload, poll, then read. Azure AI Vision spatial analysis solves the opposite problem, counting and tracking the presence of people in live feeds for operational questions, under real privacy obligations. Choosing correctly between content discovery and operational presence is most of the skill. Next, in **Knowledge mining with Azure AI Search**, you'll take transcripts and documents like these and build the index that makes an entire corpus findable.

## Further learning

- [What is Azure AI Video Indexer?](https://learn.microsoft.com/en-us/azure/azure-video-indexer/video-indexer-overview)
- [Azure AI Video Indexer insights overview](https://learn.microsoft.com/en-us/azure/azure-video-indexer/insights-overview)
- [What is spatial analysis?](https://learn.microsoft.com/en-us/azure/ai-services/computer-vision/intro-to-spatial-analysis-public-preview)
- [Azure AI Video Indexer API guide](https://learn.microsoft.com/en-us/azure/azure-video-indexer/video-indexer-use-apis)
