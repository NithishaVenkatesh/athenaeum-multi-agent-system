---
kind: module
id: as-c01-m01
vertical: architecture-security
course_id: as-c01
title: Designing compute solutions
level: foundational
grounded_on: "AZ-305 skills outline (2026-04-17), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-305
synthetic: true
order: 1
prereqs: []
objectives:
  - Derive compute requirements from a workload description
  - Recommend VM, container, serverless, and batch compute with a clear rationale
  - Design compute for batch and bursty processing
---

# Designing compute solutions

A platform team at Solstice Tickets, a fictional events marketplace, hands you four jobs and asks "where should each one run?" There is a legacy .NET monolith that must keep its filesystem-based session state; a new set of stateless pricing APIs; a webhook that fires only when a partner posts a sale; and an overnight job that renders 200,000 PDF tickets in a two-hour window. Pick wrong and you either overpay for idle capacity or hit a wall when load arrives. The skill this module teaches is not "what is Azure Functions" — it is how to read those four sentences and map each to the compute model that fits.

## Learning objectives

By the end of this module you will be able to:

- Extract the requirements that actually drive a compute decision from a workload description.
- Recommend between virtual machines, containers, serverless, and batch compute and defend the choice.
- Design compute for batch and bursty workloads without paying for permanent idle capacity.
- Express a compute recommendation as a reviewable decision matrix.

## Concepts

### The four requirements that drive every compute decision

Before naming a service, name the constraints. Four questions decide almost every compute recommendation.

**State.** Does the workload need to remember things on local disk between requests? A monolith that writes session files to `/tmp` is *stateful in place*; a pricing API that reads everything from a database is *stateless*. Stateless workloads can be killed and replaced freely, which unlocks serverless and aggressive autoscaling. Stateful-in-place workloads resist that and often push you toward VMs or carefully configured persistent volumes.

**Control surface.** How much of the OS do you need to own? If the workload requires a specific kernel module, a custom systemd service, or GPU drivers you patch yourself, you need a virtual machine. If it just needs "a Linux process with these dependencies," a container is a smaller, faster-to-scale unit. If it is "run this function when an event arrives," serverless removes the host from your concern entirely.

**Load shape.** Is demand steady, spiky, or absent most of the time? Steady load is cheapest on reserved VMs. Spiky load wants something that scales out fast and scales *to zero* between bursts — that is where consumption-based serverless and scale-to-zero container platforms win. A webhook that fires twice an hour should not pay for a running server 24/7.

**Time bound.** Is there a deadline, like "all tickets rendered before the 6 a.m. cutoff"? Deadlines plus high parallelism point at a batch service that can fan a job across many nodes and then release them.

### The compute spectrum, from most control to least

Think of Azure compute as a spectrum trading control for operational burden.

At the high-control end, **Azure Virtual Machines** give you the full OS. You patch it, you size it, you pay for it whether it is busy or not. Choose VMs when you genuinely need OS-level control, have licensing tied to a host, or are lifting-and-shifting something not yet containerized.

In the middle, **containers** package the app and its dependencies into an immutable image. Azure runs them in several ways: **Azure Container Instances (ACI)** for a single short-lived or isolated container with no orchestrator; **Azure Container Apps** for microservices that need scaling, revisions, and scale-to-zero without you managing Kubernetes; and **Azure Kubernetes Service (AKS)** when you need full Kubernetes control and are prepared to operate it.

At the low-control end, **Azure Functions** runs your code in response to a trigger and, on the Consumption plan, bills per execution and scales to zero when idle. You own the function; Azure owns everything else. The tradeoff is constraints: execution-time limits, cold starts, and a programming model built around short, event-driven units of work. **Azure App Service** sits nearby for always-on web apps that want a managed platform without the event-driven model — verify current plan limits in the docs, as they change.

For deadline-bound parallel work, **Azure Batch** schedules a job across a pool of compute nodes, runs your tasks, and tears the pool down. It is purpose-built for the "render 200,000 PDFs by 6 a.m." shape that would be wasteful on always-on infrastructure.

### Cost follows the load shape, not the logo

The single most common architecture mistake is choosing a compute model by familiarity rather than by load shape. A VM that runs at 5% utilization is almost pure waste; the same workload on a consumption plan might cost a tenth as much. Conversely, a steady, high-throughput service on per-execution serverless billing can cost *more* than a reserved VM, because you are paying a premium for elasticity you do not use. The rule of thumb: steady and predictable favors reserved capacity; spiky and intermittent favors consumption; deadline-bound bursts favor batch. Always sanity-check the recommendation against the workload's real duty cycle.

## Walkthrough: placing the four Solstice Tickets workloads

Work the four jobs through the requirements grid, then capture the result as a decision matrix an architect can defend in review.

```text
Workload              State        Control   Load shape    Time-bound  -> Recommendation
--------------------  -----------  --------  ------------  ----------  -----------------------
Legacy .NET monolith  stateful     OS-level  steady        no          Azure Virtual Machine
Stateless pricing API stateless    process   spiky          no         Azure Container Apps
Partner-sale webhook  stateless    none      intermittent  no          Azure Functions (Consumption)
Overnight PDF render  stateless    process   burst          yes        Azure Batch
```

The reasoning, row by row: the monolith's filesystem session state and OS dependencies rule out scale-to-zero models, so it lands on a VM (a candidate for later modernization, not a forever home). The pricing API is stateless and spiky, so Container Apps gives autoscaling and scale-to-zero with no cluster to operate. The webhook fires rarely and statelessly — Functions on Consumption pays only per invocation. The render job is a deadline-bound parallel burst, the canonical Batch use case.

Now provision the scale-to-zero pricing API with `az` to make the recommendation concrete:

```bash
# Create a Container Apps environment, then a scale-to-zero pricing API.
az containerapp env create \
  --name solstice-prod-env \
  --resource-group solstice-prod-rg \
  --location eastus

az containerapp create \
  --name pricing-api \
  --resource-group solstice-prod-rg \
  --environment solstice-prod-env \
  --image solsticeacr.azurecr.io/pricing-api:1.4.0 \
  --target-port 8080 \
  --ingress external \
  --min-replicas 0 \
  --max-replicas 20 \
  --cpu 0.5 --memory 1.0Gi
```

`--min-replicas 0` is the load-shape decision made executable: when no traffic arrives, the app scales to zero and you stop paying for compute; `--max-replicas 20` caps the blast radius of a traffic spike. Observe that nothing here mentions servers or a cluster — that operational burden is exactly what you traded away by choosing Container Apps over AKS for this workload.

## Common pitfalls

- **Choosing compute by familiarity instead of load shape.** "We always use VMs" is how steady-state thinking ends up paying for idle capacity on a spiky workload. Start from the requirements grid, not the team's defaults.
- **Treating serverless as free of constraints.** Consumption-plan functions have execution-time ceilings and cold starts. A 45-minute job or a latency-critical synchronous call may be a poor fit — confirm the current limits in the docs before committing.
- **Forcing a stateful app onto scale-to-zero compute.** If the app writes session or cache data to local disk, killing and recreating instances loses it. Either externalize the state (database, cache, blob) first, or keep it on a VM until you do.
- **Reaching for AKS when Container Apps would do.** Kubernetes is powerful and *expensive to operate*. If you do not need custom controllers or fine-grained pod control, the managed serverless container platform removes a standing operational cost.
- **Ignoring the duty cycle when costing serverless.** Per-execution billing is cheap when idle and can be costly at sustained high throughput. Estimate executions per month before assuming serverless is cheaper.

## Knowledge check

1. A reporting service runs a steady 70% CPU all day, every day, with no traffic spikes. Why is a Consumption-plan serverless model likely the *wrong* recommendation?
2. Two stateless microservices have spiky, unpredictable traffic and no need for custom Kubernetes controllers. What compute model fits, and which single setting most directly controls idle cost?
3. A job must transcode 50,000 videos before an 8 a.m. SLA and is embarrassingly parallel. Why is Azure Batch a better fit than scaling up a single large VM?

<details>
<summary>Answers</summary>

1. Serverless consumption billing is priced for intermittent load; a workload running near-continuously pays an elasticity premium it never uses, so reserved VM capacity is usually cheaper — cost follows load shape, not the service logo.
2. Azure Container Apps; `--min-replicas 0` (scale-to-zero) is the setting that most directly eliminates idle cost between bursts while autoscaling handles the spikes.
3. Batch fans the work across a pool of many nodes in parallel and tears it down afterward, meeting the deadline through breadth rather than a single tall VM whose serial throughput would miss the SLA and which would sit idle the rest of the day.

</details>

## Summary

Compute design starts with four questions — state, control, load shape, and time bound — and ends with a service whose billing and scaling model matches the workload's duty cycle. Walking those constraints through a decision matrix turns "where should this run" from a habit into a defensible recommendation, and surfaces cost mistakes before they reach a bill. The next module, *Designing network solutions*, asks the matching question for connectivity: once these workloads are placed, how do they reach the internet, on-premises systems, and each other safely and quickly?

## Further learning

- [Choose an Azure compute service](https://learn.microsoft.com/en-us/azure/architecture/guide/technology-choices/compute-decision-tree)
- [Azure Container Apps overview](https://learn.microsoft.com/en-us/azure/container-apps/overview)
- [Azure Functions hosting options](https://learn.microsoft.com/en-us/azure/azure-functions/functions-scale)
- [Azure Batch documentation](https://learn.microsoft.com/en-us/azure/batch/batch-technical-overview)
