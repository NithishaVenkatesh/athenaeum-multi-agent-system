---
kind: module
id: de-c02-m03
vertical: data-engineering
course_id: de-c02
title: Orchestrating pipelines with Data Factory
level: intermediate
grounded_on: "DP-203 skills outline (2024-10-24), paraphrased — original synthetic content; current path Fabric DP-700"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/dp-203
synthetic: true
order: 3
prereqs: [de-c02-m02]
objectives:
  - Build pipelines in Azure Data Factory or Synapse Pipelines that orchestrate activities
  - Schedule and trigger batch runs with the right trigger type
  - Version pipeline artifacts with Git integration and parameterize for reuse
---

# Orchestrating pipelines with Data Factory

You now have a Spark notebook that cleans Greenfork's sales feed and T-SQL that shreds the supplier JSON. But right now *you* run them — by hand, in the right order, hoping the file has landed. That does not scale and it does not survive your vacation. The Spark job must wait for the file, then run; the SQL load must run only if the Spark job succeeded; the whole thing must fire every night at 2 a.m. without a human; and when a teammate changes the pipeline, you need to review the change, not discover it in production. This is orchestration, and in the Azure data world the orchestrator is **Azure Data Factory** (or the equivalent **Synapse Pipelines**, which share the same engine).

## Learning objectives

By the end of this module you will be able to:

- Compose a pipeline from activities with explicit success/failure dependencies
- Parameterize a pipeline so one definition serves many runs
- Choose and configure the right trigger type for a batch schedule
- Put pipeline artifacts under Git version control and understand publish vs. commit

## Concepts

### Pipelines, activities, and dependency chains

A **pipeline** is a directed graph of **activities**. An activity is one unit of work — run a notebook, execute a stored procedure, copy a dataset, run a Synapse Spark job, call another pipeline. Activities are connected by *dependency conditions*: the SQL-load activity runs only when the Spark activity completes with `Succeeded`; a cleanup activity might run on `Completion` (success *or* failure); an alert might run on `Failed`. This is how you encode "do B only if A worked" without writing control-flow code yourself.

Beyond plain dependencies, control activities give you real logic: `If Condition` branches, `ForEach` iterates over a collection (for example, loop over every store's file), `Until` retries, and `Execute Pipeline` lets you compose smaller pipelines into bigger ones. The mental model: the pipeline is your batch *program*, activities are its statements, and the dependency edges are its control flow — all declarative, all observable in the monitoring view.

### Parameters and the integration runtime

Hardcoding a date or a file path into a pipeline means a new pipeline for every day. Instead you **parameterize**. Pipeline parameters are passed at trigger time; you reference them in activity settings with expressions like `@pipeline().parameters.runDate`. System variables such as `@pipeline().TriggerTime` and functions like `@formatDateTime(...)` let a single definition compute "yesterday's folder" on every run. Parameterization is what turns one pipeline into a reusable, schedule-driven program.

Where the work physically runs is the **integration runtime** (IR). The Azure (auto-resolve) IR handles cloud-to-cloud movement and transforms; a self-hosted IR reaches into a private network or on-premises source. You rarely touch it for pure-cloud batch, but knowing it exists explains where copy and transform compute lives and how to reach data behind a firewall.

### Triggers: how a batch starts itself

A pipeline does nothing until something *triggers* it. There are three kinds worth knowing. A **schedule trigger** fires on a wall-clock recurrence — every night at 02:00. A **tumbling window trigger** fires for fixed, contiguous, non-overlapping time slices and, importantly, tracks state and supports backfill and dependency between windows — the right choice when each run owns a specific time slice and you may need to replay missed slices. An **event-based (storage) trigger** fires when a blob is created or deleted, so the pipeline starts the moment the vendor's file lands instead of guessing at a time. Choosing the trigger is choosing the *semantics* of your batch: clock-driven, slice-driven, or arrival-driven.

### Version control: publish is not the same as commit

By default, changes you make in the authoring UI are saved to the Data Factory service when you *publish* — and there is no history, no review, no rollback. The professional setup connects the factory to a **Git repository** (Azure Repos or GitHub). With Git integration, your edits are committed to a working branch as JSON artifacts; you open a pull request; a teammate reviews the diff; you merge to the collaboration branch; and only then do you *publish* to the live service from that branch. The artifacts — pipelines, datasets, linked services, triggers — are just JSON, so they diff and review like any code. The distinction to internalize: **commit** captures intent and history in Git; **publish** deploys the collaboration branch to the running service. Treat publish as a deployment step, not a save button.

## Walkthrough: the nightly Greenfork pipeline

You will define a pipeline that runs the sales-cleaning notebook, then — only on success — runs the supplier-shred stored procedure, and schedule it for 02:00 daily. Pipelines are JSON; this is the artifact you would commit to Git. (In practice you author in the UI, but reading the JSON is how you review a teammate's change.)

```json
{
  "name": "pl_nightly_batch",
  "properties": {
    "parameters": {
      "runDate": { "type": "string" }
    },
    "activities": [
      {
        "name": "Clean_Sales_Spark",
        "type": "SynapseNotebook",
        "typeProperties": {
          "notebook": { "referenceName": "nb_clean_sales", "type": "NotebookReference" },
          "parameters": {
            "run_date": { "value": "@pipeline().parameters.runDate", "type": "string" }
          }
        },
        "policy": { "timeout": "0.02:00:00", "retry": 2, "retryIntervalInSeconds": 300 }
      },
      {
        "name": "Shred_Supplier_JSON",
        "type": "SqlPoolStoredProcedure",
        "dependsOn": [
          { "activity": "Clean_Sales_Spark", "dependencyConditions": [ "Succeeded" ] }
        ],
        "typeProperties": {
          "storedProcedureName": "[gold].[usp_load_deliveries]",
          "storedProcedureParameters": {
            "RunDate": { "value": "@pipeline().parameters.runDate", "type": "String" }
          }
        }
      }
    ]
  }
}
```

The `dependsOn` block with `"Succeeded"` is the load-bearing line: the stored procedure runs only if the notebook succeeded, so a bad Spark run never feeds half-clean data into the warehouse. The notebook activity has a `retry` policy, so a transient cluster hiccup retries twice before failing the pipeline. Now attach a schedule trigger:

```json
{
  "name": "tr_nightly_0200",
  "properties": {
    "type": "ScheduleTrigger",
    "typeProperties": {
      "recurrence": {
        "frequency": "Day",
        "interval": 1,
        "startTime": "2026-06-13T02:00:00Z",
        "timeZone": "UTC"
      }
    },
    "pipelines": [
      {
        "pipelineReference": { "referenceName": "pl_nightly_batch", "type": "PipelineReference" },
        "parameters": { "runDate": "@formatDateTime(trigger().scheduledTime, 'yyyy-MM-dd')" }
      }
    ]
  }
}
```

The trigger passes the scheduled date into the pipeline's `runDate` parameter, so each night's run cleans the correct folder with no hardcoding. Commit both JSON artifacts to your Git working branch, open a PR, and publish from the collaboration branch after review.

## Common pitfalls

- **Using "Completion" where you meant "Succeeded".** A dependency on `Completion` runs the next activity even when the previous one failed, silently loading bad data. Use `Succeeded` for the happy path; reserve `Completion` for cleanup.
- **Hardcoding dates and paths.** A pipeline with a literal `2026-06-12` only works for one day. Parameterize and compute the date from the trigger time.
- **Treating publish as version control.** Publishing without Git gives you no history, no review, no rollback. Connect Git, commit to a branch, review by PR, then publish.
- **Wrong trigger for the semantics.** Using a plain schedule trigger when each run owns a time slice you may need to backfill costs you replay capability. Use a tumbling window trigger when slices and backfill matter.
- **No retry or timeout on flaky activities.** Without a retry policy a transient failure kills the whole run. Set sensible `retry`, `retryIntervalInSeconds`, and `timeout` on activities that touch external systems.

## Knowledge check

1. Your second activity must run *only* when the first succeeds, but it currently runs even after the first fails. What dependency condition is misconfigured?
2. The business wants the pipeline to start the instant the vendor's file lands in the lake, not at a fixed time. Which trigger type fits, and why not a schedule trigger?
3. A teammate published a pipeline change that broke production and there is no way to roll back. What was missing from the setup, and how does it prevent this?

<details>
<summary>Answers</summary>

1. The dependency is set to `Completion` (or `Failed`) instead of `Succeeded`. Change it to `Succeeded` so the downstream activity runs only on a successful upstream completion. — Dependency conditions encode the success/failure contract between activities.
2. An event-based (storage) trigger that fires on blob creation. A schedule trigger fires on the clock and would either run before the file arrives or waste time waiting. — Arrival-driven semantics call for an event trigger, not a clock-driven one.
3. Git integration was missing. With Git, changes are committed to a branch and reviewed via pull request, and you can revert a commit and republish, giving history, review, and rollback that publish-only cannot. — Publish deploys; Git provides the version history and review gate.

</details>

## Summary

A pipeline is your batch program: activities are statements, dependency conditions are control flow, parameters make it reusable, and a trigger decides when and how it starts — by clock, by time slice, or by file arrival. You also separated *publish* (deploy to the live service) from *commit* (capture history in Git for review and rollback). With orchestration in place, the final module, **Incremental loads, upserts, and error handling**, makes each run process only new data, apply changes idempotently, and recover cleanly when something fails.

## Further learning

- [Pipelines and activities in Azure Data Factory and Azure Synapse Analytics](https://learn.microsoft.com/en-us/azure/data-factory/concepts-pipelines-activities)
- [Pipeline execution and triggers in Azure Data Factory or Azure Synapse Analytics](https://learn.microsoft.com/en-us/azure/data-factory/concepts-pipeline-execution-triggers)
- [Source control in Azure Data Factory](https://learn.microsoft.com/en-us/azure/data-factory/source-control)
- [Create a tumbling window trigger](https://learn.microsoft.com/en-us/azure/data-factory/how-to-create-tumbling-window-trigger)
