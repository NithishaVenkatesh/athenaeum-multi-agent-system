---
kind: module
id: cb-c02-m04
vertical: cloud-backend
course_id: cb-c02
title: Data lifecycle and storage policies
level: intermediate
grounded_on: "AZ-204 skills outline (2026-01-14), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-204
synthetic: true
order: 4
prereqs: [cb-c02-m03]
objectives:
  - Implement lifecycle management policies that tier and expire blobs automatically
  - Automate aging of data across hot, cool, and archive tiers
  - Apply data protection options such as soft delete and versioning to blobs
---

# Data lifecycle and storage policies

In **Azure Blob Storage with the SDK** you saw Meridian Parcel's plan: keep proof-of-delivery photos hot this month, cool them once they stop being viewed, and archive them for the legal retention window. The problem is that nobody wants to write — or trust — a nightly script that walks millions of blobs deciding which to move or delete. Hand-rolled cleanup jobs are exactly where data either lingers and runs up the bill or gets deleted too aggressively and triggers a compliance incident. The storage account can do this work itself, on a schedule, declaratively. This module teaches you to express retention and tiering as **lifecycle management policy** and to turn on the protection features that make automated deletion safe. The goal: storage that tiers and expires itself correctly while you sleep.

## Learning objectives

By the end of this module you will be able to:

- Author a lifecycle management policy that tiers and deletes blobs based on age.
- Scope policy rules to a subset of blobs using prefixes and blob types.
- Explain how policy evaluation runs and why changes are not instantaneous.
- Apply soft delete and versioning so automated lifecycle actions are recoverable.

## Concepts

### Lifecycle policy as declarative rules

A **lifecycle management policy** is a JSON document attached to the storage account. It contains **rules**, each with a **filter** (which blobs the rule applies to — by prefix, blob type, and optionally index tags) and a set of **actions** keyed to age. The actions are the lifecycle verbs: move a block blob to cool, move it to archive, or delete it, each triggered after a number of days since creation or since last access/modification.

The shift in thinking is from imperative ("loop over blobs and decide") to declarative ("blobs under `proof-of-delivery/` that haven't been modified in 30 days belong in cool; after 365 days, archive; after 2,555 days, delete"). You describe the desired end state and the platform enforces it continuously. No compute to run, no job to monitor, no off-by-one bug walking a paginated listing of millions of objects.

### How and when rules run

A policy does not act the instant you save it. The platform runs lifecycle evaluation on its own cadence — commonly described as roughly once a day — so a newly added rule can take up to about 24 hours to first execute, and "after 30 days" means "on the next evaluation pass after the blob is 30 days old," not to the minute. This matters for expectations: do not write tests that assume a blob tiers seconds after crossing the threshold. The age clock is driven by blob timestamps (creation, last modified, or last accessed, depending on the condition you choose); enabling last-access tracking has its own setting you turn on at the account level. Treat exact timings as "verify in the docs," but design around the principle that lifecycle is eventually-consistent housekeeping, not a real-time trigger.

### Protecting data so automation is safe

Automated deletion is only acceptable if mistakes are recoverable. Two account features provide that safety net. **Blob soft delete** retains deleted blobs for a configurable retention period, so an accidental delete — whether by a person or by a policy rule — can be undone within the window before the data is purged for good. **Blob versioning** automatically keeps a previous version whenever a blob is overwritten or deleted, so you can restore the prior state. Turn both on *before* you let lifecycle rules delete anything; together they convert "the policy deleted the wrong thing" from a data-loss event into a quick restore. A complementary point-in-time control for stricter compliance is an immutability policy (legal hold or time-based retention), which prevents modification or deletion for a fixed period — useful when retention is a legal requirement rather than a preference.

## Walkthrough: automating Meridian's photo retention

You will attach a lifecycle policy that tiers proof-of-delivery photos to cool after 30 days, to archive after a year, and deletes them after seven years, scoped to that container's prefix. The policy is expressed as JSON and applied with the Azure CLI; in production you would commit this JSON to source control and apply it through your pipeline.

```bash
# Save the policy. The filter scopes it to one prefix and block blobs only;
# actions are keyed to days since last modification.
cat > pod-lifecycle.json <<'JSON'
{
  "rules": [
    {
      "enabled": true,
      "name": "proof-of-delivery-aging",
      "type": "Lifecycle",
      "definition": {
        "filters": {
          "blobTypes": ["blockBlob"],
          "prefixMatch": ["proof-of-delivery/"]
        },
        "actions": {
          "baseBlob": {
            "tierToCool":    { "daysAfterModificationGreaterThan": 30 },
            "tierToArchive": { "daysAfterModificationGreaterThan": 365 },
            "delete":        { "daysAfterModificationGreaterThan": 2555 }
          }
        }
      }
    }
  ]
}
JSON

# Turn on protection FIRST so policy deletes are recoverable.
az storage account blob-service-properties update \
  --account-name meridianstg --resource-group meridian-rg \
  --enable-delete-retention true --delete-retention-days 14 \
  --enable-versioning true

# Apply the lifecycle policy to the account.
az storage account management-policy create \
  --account-name meridianstg --resource-group meridian-rg \
  --policy @pod-lifecycle.json
```

Read the rule top to bottom: it targets only block blobs whose names start with `proof-of-delivery/`, leaving every other container untouched. The three actions form an aging ladder driven by how long it has been since each blob was modified. Before applying it, you enable 14-day soft delete and versioning, so if the prefix or a threshold is ever wrong, the affected blobs are recoverable rather than gone. After applying, expect the first evaluation pass within roughly a day — not immediately.

## Common pitfalls

- **Expecting instant effect.** Lifecycle runs on a periodic evaluation cadence; rules can take up to about a day to first execute and act on the next pass after a threshold, not to the second. Don't debug a "broken" policy minutes after saving it.
- **Deleting without a safety net.** A wrong prefix or off-by-one day threshold can purge live data. Enable soft delete and versioning *before* adding any `delete` action so mistakes are recoverable.
- **Archiving data you still read.** A rule that archives blobs your application still requests turns fast reads into multi-hour rehydration. Tier to archive only what is genuinely cold.
- **Overly broad filters.** A rule with no `prefixMatch` applies to the whole account. Scope filters to the exact prefix and blob type you mean, and review the rule's reach before enabling it.
- **Confusing lifecycle expiry with immutability.** Lifecycle deletes on a schedule; it does not prevent early deletion. If retention is a legal requirement, add an immutability (time-based retention or legal hold) policy as well.

## Knowledge check

1. You add a rule to archive blobs after 90 days and a few minutes later the tier is unchanged. Is the policy broken? Explain.
2. Why should soft delete and versioning be enabled before, not after, you introduce a `delete` action in a lifecycle policy?
3. A rule was meant for the `proof-of-delivery/` prefix but omitted `prefixMatch`, and it deletes after 2,555 days. What is the risk, and what is the fix?

<details>
<summary>Answers</summary>

1. Not broken. Lifecycle evaluation runs periodically (roughly daily); a new rule can take up to about a day to first run and acts on the next pass after the age threshold, not instantly. — Lifecycle is scheduled housekeeping, not a real-time trigger.
2. So that an erroneous policy delete is recoverable. Enabling them after the fact does not protect data already purged. Turning them on first means any mistaken deletion can be restored within the retention window. — Protection must exist before the destructive action runs.
3. Without `prefixMatch`, the rule applies account-wide and will eventually delete blobs in every container. Add the `prefixMatch: ["proof-of-delivery/"]` filter (and the `blockBlob` type filter) to scope it. — Unscoped filters match all blobs.

</details>

## Summary

Lifecycle management lets the storage account tier and expire data declaratively: write rules with filters and age-based actions, scope them tightly, and let the platform enforce them on its evaluation schedule rather than running fragile cleanup jobs. Pair every deletion with soft delete and versioning so automation is recoverable, and reach for immutability policies when retention is legally mandated. With this module you complete the data layer — Cosmos DB for structured items, the change feed for reacting to writes, Blob Storage for objects, and policies that keep all of it cost-efficient and compliant. The next course, **Securing & Integrating Cloud Applications** (cb-c03), builds identity, secrets, and messaging on top of everything you have stored here.

## Further learning

- [Optimize costs by automatically managing the data lifecycle](https://learn.microsoft.com/en-us/azure/storage/blobs/lifecycle-management-overview)
- [Configure a lifecycle management policy](https://learn.microsoft.com/en-us/azure/storage/blobs/lifecycle-management-policy-configure)
- [Soft delete for blobs](https://learn.microsoft.com/en-us/azure/storage/blobs/soft-delete-blob-overview)
- [Blob versioning](https://learn.microsoft.com/en-us/azure/storage/blobs/versioning-overview)
