---
kind: module
id: cb-c02-m03
vertical: cloud-backend
course_id: cb-c02
title: Azure Blob Storage with the SDK
level: intermediate
grounded_on: "AZ-204 skills outline (2026-01-14), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-204
synthetic: true
order: 3
prereqs: [cb-c02-m01]
objectives:
  - Perform blob operations (upload, download, list, delete) using the SDK
  - Set and retrieve system properties and custom metadata on blobs
  - Choose access tiers to balance cost against retrieval latency
---

# Azure Blob Storage with the SDK

Meridian Parcel's delivery records live in Cosmos DB, but couriers also snap a photo at each drop-off as proof of delivery. Storing a two-megapixel JPEG inside a Cosmos item is exactly the mistake module 1 warned against: it bloats item size, inflates RU costs on every read, and hits document size limits. Photos, scanned waybills, exported reports, and backups are **unstructured data** — large opaque payloads you store and serve whole. Azure Blob Storage is built for precisely this, and at a fraction of the cost per gigabyte. In this module you learn to put those objects where they belong, attach the metadata that lets you find and govern them, and pick the access tier that keeps the storage bill sane. The Cosmos item keeps a small pointer (a blob URL); the bytes live in Blob Storage.

## Learning objectives

By the end of this module you will be able to:

- Upload, download, list, and delete blobs using the Storage SDK with a credential instead of an embedded key.
- Distinguish containers, blob types, and the role of each.
- Set and read system properties (like content type) and custom metadata.
- Select hot, cool, cold, or archive access tiers based on access frequency.

## Concepts

### Accounts, containers, and blobs

A **storage account** is the top-level namespace; inside it you create **containers** (flat buckets, not nested folders), and inside containers you store **blobs**. A blob name may contain slashes (`2026/06/dlv-90187.jpg`), which tools render as a folder tree, but the structure is virtual — there are no real directories, just names. The most common blob type is the **block blob**, optimized for upload-and-serve workloads like images and documents; append blobs suit logging and page blobs back disk scenarios. For Meridian's proof-of-delivery photos, block blobs are the right choice.

Every blob has a URL of the form `https://<account>.blob.core.windows.net/<container>/<blobname>`. That URL is what you store in the Cosmos item, keeping the database lean while the object lives in storage built to stream bytes.

### Properties versus metadata

Two kinds of attributes ride along with a blob, and confusing them causes real bugs. **System properties** are defined by the service — `Content-Type`, `Content-Encoding`, `ETag`, last-modified time, content length. They affect how the blob is served: set `Content-Type` to `image/jpeg` and a browser renders the photo; leave it as the default `application/octet-stream` and the browser downloads it instead. **Custom metadata** is your own set of name/value string pairs (for example `customerId=cust-4521`, `capturedBy=courier-77`) stored on the blob. Metadata is great for tagging and filtering in your own code, but note it is *not* indexed for server-side query by default — to search across blobs by metadata you would use blob index tags or an external index. Keep both in mind: set the content type so the object serves correctly, and use metadata to carry context the object would otherwise lose.

### Access tiers: paying for the access pattern you actually have

Blob Storage charges differently depending on how often you expect to touch data. The **hot** tier has the lowest access cost and highest storage cost — right for data read frequently. **Cool** and **cold** lower the storage cost in exchange for higher per-access cost and minimum-retention expectations, suited to data accessed infrequently but still occasionally. **Archive** is the cheapest storage but is *offline*: a blob there must be **rehydrated** (which can take hours) before you can read it, so it fits compliance copies you almost never open. Exact prices and minimum-stay rules change, so verify current numbers in the docs; the durable idea is to match the tier to the read pattern. Meridian keeps this month's delivery photos in hot, ages them to cool after they stop being viewed, and archives them for the legal retention window — which you will automate in module 4.

## Walkthrough: storing proof-of-delivery photos

You will upload a courier's photo to a `proof-of-delivery` container, set its content type, attach metadata linking it to the delivery, then read the metadata back. The Python SDK (`azure-storage-blob`) authenticates with `DefaultAzureCredential` — same credential model as Cosmos, no account key in code.

```python
import os
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.identity import DefaultAzureCredential

account_url = os.environ["BLOB_ACCOUNT_URL"]  # https://meridianstg.blob.core.windows.net
service = BlobServiceClient(account_url, credential=DefaultAzureCredential())

container = service.get_container_client("proof-of-delivery")
container.create_container()  # raises if it already exists; guard in real code

blob = container.get_blob_client("2026/06/dlv-90187.jpg")

with open("delivery-photo.jpg", "rb") as f:
    blob.upload_blob(
        f,
        overwrite=True,
        # System property: makes browsers render the image instead of downloading.
        content_settings=ContentSettings(content_type="image/jpeg"),
        # Custom metadata: your own searchable-in-code context.
        metadata={"customerId": "cust-4521", "capturedBy": "courier-77"},
    )

# Read it all back: properties carry system info, metadata carries your tags.
props = blob.get_blob_properties()
print(props.content_settings.content_type)        # image/jpeg
print(props.size, "bytes")
print(props.metadata["customerId"])               # cust-4521
print(props.blob_tier)                             # Hot (the account default)
```

The upload does three jobs at once: it streams the bytes, sets the content type so the blob serves as an image, and tags it with the delivery's customer. Reading `get_blob_properties()` returns both the service-defined fields (content type, size, tier) and your metadata in one call. You would then write `blob.url` into the matching Cosmos delivery item, so the record points at the photo without carrying it.

## Common pitfalls

- **Forgetting `Content-Type`.** Without it, blobs default to `application/octet-stream` and browsers download rather than display them. Set it on upload via `ContentSettings`.
- **Confusing metadata with queryable storage.** Custom metadata is per-blob and not indexed for server-side search by default. To filter many blobs by attribute, use blob index tags or maintain an external index — don't list-and-scan a huge container.
- **Overwriting blobs accidentally — or refusing to.** `upload_blob` without `overwrite=True` fails if the blob exists; with it, you silently replace data. Decide intentionally and consider conditional requests (ETag) to avoid lost updates.
- **Reading from the archive tier directly.** Archive blobs are offline; a read fails until you rehydrate, which can take hours. Never put latency-sensitive data in archive.
- **Embedding account keys in code or config.** Use `DefaultAzureCredential` with a managed identity and role assignments (Storage Blob Data Contributor), not a connection string with a shared key. You will harden this further in cb-c03.

## Knowledge check

1. A teammate stored delivery photos as base64 strings inside Cosmos items and read costs have spiked. What is the better design and why?
2. Uploaded images download instead of displaying in the browser. What property is likely wrong, and where do you set it?
3. The team wants the cheapest storage for seven-year legal-retention copies they expect to never open. Which tier, and what is the catch when one is finally requested?

<details>
<summary>Answers</summary>

1. Store the photo as a block blob and keep only the blob URL in the Cosmos item. — Large payloads inflate item size and RU charges on every read; Blob Storage is cheaper per GB and built to stream bytes.
2. `Content-Type` is missing or wrong (defaulting to `application/octet-stream`). Set it via `ContentSettings(content_type="image/jpeg")` on upload, or update the blob's properties. — The content type controls how the object is served.
3. Archive tier. The catch: archive is offline, so any read requires rehydration that can take hours before the blob is accessible. — Archive trades the lowest storage cost for high retrieval latency.

</details>

## Summary

Blob Storage is where unstructured data belongs: store the object, set its content type so it serves correctly, tag it with metadata for context, and keep a small URL pointer in your database rather than the bytes. Access tiers let you pay for the read pattern you actually have, from hot down to offline archive. With objects landing correctly and tiered sensibly, the final module — **Data lifecycle and storage policies** — automates the aging, tiering, and expiry you are currently doing by hand.

## Further learning

- [Introduction to Azure Blob Storage](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-blobs-introduction)
- [Quickstart: Azure Blob Storage client library for Python](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-quickstart-blobs-python)
- [Manage blob properties and metadata with Python](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-blob-properties-metadata-python)
- [Access tiers for blob data](https://learn.microsoft.com/en-us/azure/storage/blobs/access-tiers-overview)
