---
kind: module
id: cb-c01-m02
vertical: cloud-backend
course_id: cb-c01
title: Event-driven code with Azure Functions
level: foundational
grounded_on: "AZ-204 skills outline (2026-01-14), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-204
synthetic: true
order: 2
prereqs: [cb-c01-m01]
objectives:
  - Create and configure an Azure Functions app
  - Implement triggers using timers, webhooks, and data operations
  - Wire input and output bindings to reduce boilerplate
---

# Event-driven code with Azure Functions

Northwind Parcel's orders API from the previous module works, but the team keeps bolting awkward background jobs onto it: a nightly task that expires stale carts, a webhook that fires when a payment provider confirms a charge, a small routine that thumbnails an uploaded shipping label. Running these inside a continuously-billed web app is wasteful — most of the time they do nothing, yet you pay for a server that is always on. What they actually want is code that wakes up only when there is something to do, runs, and then gets out of the way. That is the serverless model, and in Azure it is Azure Functions.

## Learning objectives

By the end of this module you will be able to:

- Create and configure a Functions app and choose an appropriate hosting plan.
- Implement triggers that run code on a schedule, on an HTTP/webhook call, and in response to data changes.
- Use input and output bindings to read and write external services without writing connection plumbing.

## Concepts

### Triggers: what makes a function run

A function does nothing until something *triggers* it. Each function has exactly one trigger, and the trigger defines both the event that starts it and the data delivered to it. A **timer trigger** runs on a CRON-style schedule — perfect for the nightly cart-expiry job. An **HTTP trigger** runs when a request hits its URL, which is how you implement webhooks and lightweight APIs. A **queue** or **blob** trigger runs when a message lands on a queue or a file appears in storage, letting one part of your system react to another asynchronously. The mental shift from the previous module: with App Service *you* keep a process alive to wait for requests; with Functions the platform watches the event source and invokes your code on your behalf.

### Bindings: declarative plumbing

Most function code spends its energy on the same chore — connect to a service, read or write some data, handle the connection lifecycle. **Bindings** let you declare those connections instead of coding them. An **input binding** hands your function data fetched from an external source before it runs; an **output binding** takes your return value and writes it somewhere after. For example, a queue-triggered function can declare an output binding to a storage table, and simply *return* an object — the runtime writes it to the table. You write business logic; the binding writes the boilerplate. A function has one trigger but can have several input and output bindings.

### Hosting plans and cold starts

How you host a Functions app shapes its cost and latency. The **Consumption** plan scales to zero and bills per execution, which is ideal for spiky, infrequent work — but a function that has been idle may incur a **cold start** while the platform spins up an instance. Premium and dedicated plans keep instances warm to avoid that latency at higher baseline cost. The trade-off is real: choose Consumption for bursty background jobs where a sub-second startup delay is fine, and a warm plan when latency must be predictable. Treat exact timeout and scaling limits as values to verify in the docs, since they differ by plan and change over time.

## Walkthrough: the cart-expiry and label-thumbnail functions

Northwind Parcel builds two functions in one Python Functions app using the v2 programming model, where triggers and bindings are declared with decorators. The first runs nightly; the second reacts to a queue message.

```python
import azure.functions as func
import datetime
import logging

app = func.FunctionApp()

# 1. Timer trigger: run every night at 02:00 UTC (NCRONTAB: sec min hour day month day-of-week)
@app.function_name(name="ExpireStaleCarts")
@app.timer_trigger(schedule="0 0 2 * * *", arg_name="timer",
                   run_on_startup=False)
def expire_stale_carts(timer: func.TimerRequest) -> None:
    now = datetime.datetime.utcnow().isoformat()
    logging.info("Cart-expiry sweep started at %s", now)
    # ... query and expire carts older than the cutoff ...


# 2. Queue trigger with a blob output binding.
#    A message on 'label-jobs' triggers the function; the return
#    value is written to the 'thumbnails' container automatically.
@app.function_name(name="MakeLabelThumbnail")
@app.queue_trigger(arg_name="msg", queue_name="label-jobs",
                   connection="STORAGE_CONNECTION")
@app.blob_output(arg_name="$return", path="thumbnails/{rand-guid}.png",
                 connection="STORAGE_CONNECTION")
def make_label_thumbnail(msg: func.QueueMessage) -> bytes:
    label_id = msg.get_body().decode("utf-8")
    logging.info("Generating thumbnail for label %s", label_id)
    thumbnail_bytes = render_thumbnail(label_id)  # your imaging logic
    return thumbnail_bytes  # output binding writes this to blob storage
```

What to observe here: the timer function never opens a connection to anything — it just runs on schedule. The queue function declares its input (the queue message) and its output (a blob) entirely in decorators; the line `return thumbnail_bytes` is the *whole* persistence step, because the `blob_output` binding routes the return value to a generated `.png` in the `thumbnails` container. The `connection="STORAGE_CONNECTION"` references an app setting holding the storage connection — the same configuration pattern from Module 1, so the secret stays out of code. Deploying is the familiar flow:

```bash
# From the function app project directory
func azure functionapp publish northwind-fn-app
```

The team sets `STORAGE_CONNECTION` as an application setting on the Functions app (just like App Service settings), and the two functions begin running: one on the clock, one whenever an upstream service drops a message on `label-jobs`.

## Common pitfalls

- **Expecting more than one trigger per function.** A function is defined by a single trigger. If you need the same logic on a timer *and* a queue, factor the work into a shared helper and write two thin trigger functions that call it.
- **Ignoring cold starts on Consumption.** A user-facing HTTP function on Consumption can feel sluggish after idle periods. If predictable latency matters, use a warm plan rather than fighting the symptom.
- **Doing connection plumbing by hand when a binding exists.** Manually opening a blob client to write output works, but you lose the declarative clarity and the runtime's connection management. Prefer the output binding unless you need fine-grained control.
- **Long-running work in a single invocation.** Functions are not meant to run for many minutes; a job that exceeds the plan's timeout is killed mid-flight. Break long work into queue-driven steps so each invocation is short and restartable.
- **Hard-coding the storage connection.** The `connection` property must name an app setting, not contain the value. Putting a literal connection string there leaks the secret and breaks per-environment configuration.

## Knowledge check

1. You need a function to run both at midnight and whenever a message arrives on a queue. Why can't one function do both, and what is the clean design?
2. A teammate writes a queue-triggered function that opens a blob client, uploads the result, and closes it. Which binding would simplify this, and what would the function body reduce to?
3. Your HTTP-triggered function on a Consumption plan is occasionally slow on the first call after a quiet night. What is happening, and what is one way to address it?

<details>
<summary>Answers</summary>

1. A function has exactly one trigger. Put the shared logic in a helper and create two functions — one timer-triggered, one queue-triggered — that both call it. — One trigger per function is a hard rule; reuse comes from factoring logic, not stacking triggers.
2. A blob output binding; the body would reduce to computing the result and `return`-ing it, with the binding handling the upload. — Output bindings replace hand-written persistence plumbing with the function's return value.
3. A cold start: the Consumption plan scaled the function to zero and must spin up an instance before serving the first request. Use a Premium/dedicated plan (or a warming strategy) to keep instances ready. — Scale-to-zero saves money but trades away first-call latency; a warm plan buys it back.

</details>

## Summary

Azure Functions lets you run code that activates only when an event occurs, billed for what it does rather than for being available. A function has one trigger — timer, HTTP/webhook, or data-change — and any number of input and output bindings that turn external reads and writes into declarations instead of plumbing. The hosting plan controls the cost-versus-latency trade, with Consumption scaling to zero at the price of occasional cold starts. With request-driven (App Service) and event-driven (Functions) compute in hand, the next module packages application code into portable containers and runs them on Azure's container services.

## Further learning

- [Azure Functions overview](https://learn.microsoft.com/en-us/azure/azure-functions/functions-overview)
- [Azure Functions triggers and bindings concepts](https://learn.microsoft.com/en-us/azure/azure-functions/functions-triggers-bindings)
- [Azure Functions hosting options](https://learn.microsoft.com/en-us/azure/azure-functions/functions-scale)
- [Timer trigger for Azure Functions](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-timer)
