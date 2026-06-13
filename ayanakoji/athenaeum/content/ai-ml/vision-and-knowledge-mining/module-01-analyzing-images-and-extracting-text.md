---
kind: module
id: ai-c03-m01
vertical: ai-ml
course_id: ai-c03
title: Analyzing images and extracting text
level: advanced
grounded_on: "AI-102 skills outline (2025-12-23), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/ai-102
synthetic: true
order: 1
prereqs: [ai-c01, ai-c02]
objectives:
  - Select the right Azure AI Vision visual features for an image-processing requirement
  - Detect objects in images and generate descriptive tags and captions
  - Extract printed and handwritten text from images using the Read OCR capability
---

# Analyzing images and extracting text

The team at Driftwood Outfitters, a fictional outdoor-gear retailer, has a problem you have probably met in a different costume. They have 400,000 product and warehouse photos with almost no usable metadata: filenames like `IMG_4471.jpg`, no alt text, no categories, and a pile of supplier invoices that were photographed on a phone and emailed in. Search returns nothing useful, the storefront fails accessibility audits, and accounts payable keys invoice totals in by hand. You cannot hire your way out of 400,000 images. You need a service that looks at a picture and tells you, in structured form, what is in it and what text it contains. That is exactly what Azure AI Vision does — and the skill is knowing which feature to ask for, because asking for all of them is slow and expensive.

## Learning objectives

By the end of this module you will be able to:

- Select the appropriate Azure AI Vision visual features for a stated requirement, instead of requesting everything by default.
- Generate captions, dense captions, and tags that describe an image's content.
- Detect objects and read their bounding-box coordinates for downstream cropping or layout work.
- Extract printed and handwritten text from images and reason about the asynchronous Read pattern.

## Concepts

### One analysis call, many features

Azure AI Vision's Image Analysis API is built around a single idea: you send an image once and ask for a *set* of visual features in the same request. Rather than calling a separate endpoint for tags, another for captions, and another for objects, you pass a list of the features you want and the service returns a single structured result containing only those sections. The features you can request include a caption (one natural-language sentence describing the whole image), dense captions (sentences for distinct regions), tags (single-word or short-phrase labels with confidence scores), objects (labels *with* bounding boxes), people, smart crops, and read (OCR). The practical discipline is to request the minimum set that answers your question. Each feature adds latency and contributes to billing, and a caption you never display is pure waste.

The reason this matters for design is that features answer different questions. "What is this image *of*?" is a caption or tags question. "*Where* in the image is the backpack?" is an object-detection question, because only objects return coordinates. "What does the label *say*?" is an OCR question. Picking the wrong feature produces technically valid output that does not solve your problem — tags will happily tell you an invoice contains "text" and "paper" without ever reading the total.

### Captions, dense captions, and tags

A caption is the service's best single sentence for the entire frame, such as "a person hiking on a mountain trail with a backpack." It is ideal for accessibility alt text and for giving a human a one-line summary. Dense captions go further: the model segments the image into regions and writes a sentence for each, which is useful when one photo contains several distinct subjects — a product shot showing a tent, a stove, and a sleeping bag together. Tags are the lightweight workhorse: a flat list of labels with confidence scores between 0 and 1, perfect for faceted search filters and bulk categorization. Captions are available in a subset of regions and languages, so if you deploy outside the supported set you fall back to tags; treat the supported-region list as something to verify in the docs rather than memorize, because it changes.

### Reading text with the Read capability

OCR in Azure AI Vision is exposed through the *read* visual feature, which handles both printed and handwritten text in the same call and returns text grouped into lines and words, each with bounding polygons and confidence. The model is line-oriented, not document-oriented: it gives you geometry and characters, not "this is the invoice total." Turning lines into meaning — finding the total, the date, the vendor — is your job, or a job for Azure AI Document Intelligence if the documents are structured forms. A useful mental model: Image Analysis Read is a camera that transcribes everything it sees, in reading order, with coordinates; you decide what the transcription *means*. For large documents and PDFs the historical pattern was an asynchronous submit-then-poll operation, whereas synchronous image analysis returns read results inline; which surface you use depends on the SDK and input type, so confirm the current call shape in the docs for your SDK version.

## Walkthrough: cataloging a Driftwood product photo

You are writing the first batch job for Driftwood. For each photo you want a caption for alt text, tags for search facets, and the objects with their boxes so the storefront can auto-crop a thumbnail to the main product. You will use the `azure-ai-vision-imageanalysis` Python SDK and authenticate with a key from an environment variable. (In production, prefer a managed identity with `DefaultAzureCredential`; a key keeps this example self-contained.)

```python
import os
from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures
from azure.core.credentials import AzureKeyCredential

client = ImageAnalysisClient(
    endpoint=os.environ["VISION_ENDPOINT"],
    credential=AzureKeyCredential(os.environ["VISION_KEY"]),
)

# Request only the features we will actually use.
with open("product_4471.jpg", "rb") as f:
    image_data = f.read()

result = client.analyze(
    image_data=image_data,
    visual_features=[
        VisualFeatures.CAPTION,
        VisualFeatures.TAGS,
        VisualFeatures.OBJECTS,
        VisualFeatures.READ,
    ],
    gender_neutral_caption=True,  # "person" instead of gendered nouns
)

if result.caption is not None:
    print(f"Alt text: {result.caption.text} "
          f"(confidence {result.caption.confidence:.2f})")

if result.tags is not None:
    facets = [t.name for t in result.tags.list if t.confidence > 0.75]
    print(f"Search facets: {facets}")

if result.objects is not None:
    for obj in result.objects.list:
        box = obj.bounding_box
        label = obj.tags[0].name if obj.tags else "object"
        print(f"{label} at x={box.x}, y={box.y}, w={box.width}, h={box.height}")

if result.read is not None:
    for block in result.read.blocks:
        for line in block.lines:
            print(f"Text line: {line.text}")
```

Run this against a product photo and you get a one-sentence caption you can drop straight into an `alt` attribute, a filtered list of high-confidence tags for the catalog's facet filters, and pixel-coordinate boxes the storefront can use to crop a clean thumbnail around the actual product. Notice the `confidence > 0.75` filter on tags: the raw list includes low-confidence guesses you would not want surfacing in search, so thresholding is part of doing this well. The `read` block, run against an invoice photo, would instead return the transcribed lines you'd hand to your invoice parser.

## Common pitfalls

- **Requesting every feature on every image.** Each visual feature adds latency and cost. Decide what the downstream system actually consumes and request only that. A thumbnail pipeline does not need OCR.
- **Trusting raw tag confidence.** Tags come back with confidence scores for a reason. Surfacing every tag, including 0.20-confidence guesses, pollutes search facets. Apply a threshold tuned to your tolerance for false positives.
- **Expecting OCR to understand documents.** The read feature transcribes text and geometry; it does not know which line is the invoice total. For structured forms reach for Document Intelligence (covered in ai-c02-m03) rather than hand-writing fragile line-position heuristics.
- **Ignoring image size and format limits.** The service enforces limits on file size and minimum/maximum dimensions, and rejects images outside them. Very large warehouse scans may need downscaling before submission; verify the current limits in the docs.
- **Assuming captions exist everywhere.** Caption generation is available in a subset of regions and languages. If your resource is in an unsupported region the call fails or omits captions, so design a tags-based fallback rather than assuming a caption is always present.

## Knowledge check

1. A storefront team wants to automatically crop each product photo to the main item. Which visual feature gives them what they need, and why won't tags or a caption do?
2. You run image analysis on a phone photo of a paper invoice and get back transcribed lines but the system still can't find the invoice total. What is the correct next step, and why?
3. Your batch job's Azure bill is higher than expected and each image takes longer than you'd like. You're requesting caption, dense captions, tags, objects, people, and read on every image to "be safe." What's the fix?

<details>
<summary>Answers</summary>

1. Object detection (the `OBJECTS` feature) — only objects return bounding-box coordinates, which a crop needs. A caption and tags describe *what* is in the image but give no location, so they can't drive a crop. — Coordinates are the deciding requirement.
2. Pass the transcribed text/geometry to Azure AI Document Intelligence (or your own parser), because Vision's read feature only transcribes characters and positions; it does not classify a line as "total." — Vision OCR is geometry and text, not document understanding.
3. Request only the features the downstream system consumes — for cataloging that's likely caption, tags, and objects, dropping dense captions, people, and read unless used. — Every feature adds latency and cost; "be safe" defaults waste both.

</details>

## Summary

Azure AI Vision's Image Analysis API turns a picture into structured data through a single call that returns whichever visual features you request — captions and tags for "what is this," objects for "where is it," and read for "what does it say." The engineering skill is selecting the minimum feature set for the requirement and thresholding confidence so you surface signal, not noise. OCR transcribes text but stops short of understanding it, which is the boundary where Document Intelligence takes over. Next, in **Custom vision models**, you'll go beyond prebuilt features and train models that recognize the categories and objects unique to your own business.

## Further learning

- [What is Image Analysis?](https://learn.microsoft.com/en-us/azure/ai-services/computer-vision/overview-image-analysis)
- [Call the Image Analysis 4.0 API](https://learn.microsoft.com/en-us/azure/ai-services/computer-vision/how-to/call-analyze-image-40)
- [OCR — Optical Character Recognition](https://learn.microsoft.com/en-us/azure/ai-services/computer-vision/overview-ocr)
- [Azure AI Vision client library for Python](https://learn.microsoft.com/en-us/python/api/overview/azure/ai-vision-imageanalysis-readme)
