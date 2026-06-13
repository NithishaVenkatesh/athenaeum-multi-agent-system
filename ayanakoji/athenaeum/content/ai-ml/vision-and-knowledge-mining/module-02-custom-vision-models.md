---
kind: module
id: ai-c03-m02
vertical: ai-ml
course_id: ai-c03
title: Custom vision models
level: advanced
grounded_on: "AI-102 skills outline (2025-12-23), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/ai-102
synthetic: true
order: 2
prereqs: [ai-c03-m01]
objectives:
  - Choose between image classification and object detection for a labeling requirement
  - Label images, train a custom model, and interpret its evaluation metrics
  - Publish a trained iteration and consume it from application code
---

# Custom vision models

The prebuilt features from **Analyzing images and extracting text** are excellent at general knowledge — they will confidently tell you a photo contains "a backpack." But Driftwood Outfitters does not sell "a backpack." They sell the Summit 45 and the Trailhead 28, and a returns clerk needs to look at a customer's photo and know *which model* came back, because the two are visually similar and refund amounts differ. No general model knows your SKUs, your defect categories, or the difference between your two nearly identical tent poles. When the categories that matter are specific to your business, you stop consuming a prebuilt model and start training your own. This module is about doing that well: choosing the right model type, labeling honestly, and reading the metrics so you ship something that actually works in the warehouse.

## Learning objectives

By the end of this module you will be able to:

- Decide whether a requirement calls for image classification or object detection.
- Build a labeled training dataset and understand why label quality dominates outcomes.
- Train a model and interpret precision, recall, and average precision rather than chasing a single accuracy number.
- Publish a model iteration and call it from application code through the prediction endpoint.

## Concepts

### Classification versus object detection

The first and most consequential decision is which kind of model to train, and it follows directly from the question you are answering. **Image classification** assigns one or more labels to the *whole* image: "this photo is a Summit 45." It answers "what is this a picture of?" **Object detection** finds *instances* within an image and returns a label plus a bounding box for each: "there is a Summit 45 here, and a damaged buckle there." It answers "what is in this image, where, and how many?"

The trap is choosing object detection out of a vague desire for more information. Object detection is dramatically more expensive to label — you draw a box around every instance in every image, not just pick a tag — and it needs more images to reach the same confidence. If Driftwood only needs to route a returned-item photo to the right SKU, classification is correct and far cheaper. If they need to count how many defective buckles appear on an assembly-line image, only object detection can do it. Match the model type to the question, then to the labeling budget.

### Labeling, and why it dominates everything

A custom vision model is only as good as its labels. The service handles the deep-learning machinery; you supply the supervision, and your supervision *is* the ground truth the model imitates. Two principles carry most of the weight. First, **balance and coverage**: include enough images per tag (a useful working floor is roughly 50 per tag, more for visually subtle distinctions; verify current guidance in the docs) and make sure each tag's images span the real variation — lighting, angle, background, partial occlusion — your model will face in production. A model trained only on clean studio shots fails on a dim warehouse phone photo. Second, **honest labels**: mislabeled or inconsistently labeled images don't just waste data, they teach the model the wrong thing, and a confident wrong model is worse than no model.

For object detection, tight, consistent bounding boxes matter: boxes that include too much background or clip the object teach fuzzy boundaries. The single highest-leverage activity in custom vision is not tuning training settings — it is curating and labeling data carefully.

### Reading the metrics that matter

After training, the service reports evaluation metrics, and reading them correctly is what separates a deployable model from a demo. **Precision** answers "when the model predicts a tag, how often is it right?" **Recall** answers "of all the images that truly have the tag, how many did the model catch?" These trade off against each other, and the right balance is a business decision: a returns-fraud screen might favor recall (catch every suspicious item, tolerate false alarms), while an auto-publish-to-storefront flow favors precision (never mislabel a product publicly). **Average precision (AP)** — and mean AP across tags for detection — summarizes the precision/recall curve into a single comparable number, useful for comparing iterations.

Beware the headline accuracy number on a skewed dataset: a model that always predicts your most common SKU can post high accuracy while being useless. Always look at per-tag precision and recall, and watch for tags with too few images, which the service typically flags. Treat a fresh model as a hypothesis to validate on data it has never seen, not as proven the moment training finishes.

## Walkthrough: a returns-triage classifier for Driftwood

Driftwood's returns team wants to drop a customer photo into a flow that predicts the SKU. You have built a project in the Custom Vision portal, uploaded and tagged a few hundred images across your SKUs, trained an iteration, reviewed its per-tag precision and recall, and published the iteration under the name `returns-triage-v3`. Now you'll consume it from the returns service using the `azure-cognitiveservices-vision-customvision` prediction SDK.

```python
import os
from azure.cognitiveservices.vision.customvision.prediction import (
    CustomVisionPredictionClient,
)
from msrest.authentication import ApiKeyCredentials

credentials = ApiKeyCredentials(
    in_headers={"Prediction-Key": os.environ["CV_PREDICTION_KEY"]}
)
predictor = CustomVisionPredictionClient(
    endpoint=os.environ["CV_PREDICTION_ENDPOINT"],
    credentials=credentials,
)

PROJECT_ID = os.environ["CV_PROJECT_ID"]
PUBLISHED_NAME = "returns-triage-v3"

with open("return_photo.jpg", "rb") as image:
    results = predictor.classify_image(
        PROJECT_ID, PUBLISHED_NAME, image.read()
    )

# Predictions come back sorted by probability, highest first.
top = results.predictions[0]
if top.probability >= 0.80:
    print(f"Routed to SKU: {top.tag_name} ({top.probability:.0%})")
else:
    print("Low confidence — sending to manual review queue")
```

The key design choice here is the `0.80` confidence gate. The model always returns a ranked list of tags with probabilities; it never refuses to answer. So *you* decide the threshold below which a prediction isn't trustworthy enough to act on automatically, routing those cases to a human. That gate is how you convert a probabilistic model into a reliable business process — and where you set it is exactly the precision/recall trade-off made operational.

## Common pitfalls

- **Choosing object detection when classification suffices.** Detection costs far more to label and needs more data. If you only need "which SKU is this," classify. Reserve detection for counting or locating instances.
- **Too few, too uniform images.** Models trained on a thin or studio-only dataset collapse on real-world input. Cover the lighting, angles, and backgrounds production will actually send, with enough images per tag.
- **Chasing a single accuracy number.** On imbalanced data, accuracy lies. Read per-tag precision and recall and pick the operating point that matches your tolerance for each kind of error.
- **No confidence threshold in the consuming app.** The prediction API always returns a top guess. Without a probability gate you'll auto-act on low-confidence predictions. Set a threshold and route the rest to review.
- **Forgetting to publish, or calling the wrong iteration.** Training produces an iteration; only a *published* iteration is callable by name at the prediction endpoint. Pointing your app at a stale published name silently serves an old model.

## Knowledge check

1. Driftwood wants to count how many cracked tent poles appear in a single assembly-line photo. Should you train a classification or an object-detection model, and why?
2. Your returns classifier reports 96% overall accuracy, but the team complains it keeps misrouting the rare Trailhead 28. What metric should you inspect, and what's likely wrong?
3. After retraining and improving the model, the returns service is still behaving like the old version. Nothing in the code changed. What did you most likely forget?

<details>
<summary>Answers</summary>

1. Object detection — counting and locating multiple instances in one image requires bounding boxes per instance, which only detection provides; classification would only label the whole image. — The requirement is "how many and where," not "what is this."
2. Per-tag precision and recall for the Trailhead 28 — high overall accuracy on an imbalanced dataset can hide poor recall on a rare class; the model likely has too few Trailhead 28 examples. — Aggregate accuracy masks per-class failure.
3. Publishing the new iteration (or repointing the app to the new published name) — only a published iteration is served, and the app calls a fixed published name, so an unpublished retrain has no effect. — Training and publishing are separate steps.

</details>

## Summary

Custom vision is what you reach for when the categories that matter are yours, not the world's. Choose classification for "what is this image" and object detection only when you genuinely need to locate or count instances, because detection's labeling cost is steep. Label data honestly and with real-world variety — that, not training settings, determines quality — and evaluate with per-tag precision, recall, and average precision rather than a single accuracy figure. Finally, remember that publishing an iteration and gating predictions by confidence are what turn a model into a dependable process. Next, in **Extracting insights from video**, you'll move from single frames to time: pulling transcripts, faces, and movement out of video and live streams.

## Further learning

- [What is Custom Vision?](https://learn.microsoft.com/en-us/azure/ai-services/custom-vision-service/overview)
- [How to improve your Custom Vision model](https://learn.microsoft.com/en-us/azure/ai-services/custom-vision-service/getting-started-improving-your-classifier)
- [Test and retrain a model with Custom Vision](https://learn.microsoft.com/en-us/azure/ai-services/custom-vision-service/test-your-model)
- [Custom Vision prediction client library for Python](https://learn.microsoft.com/en-us/python/api/overview/azure/cognitiveservices-vision-customvision-readme)
