---
kind: module
id: cb-c01-m03
vertical: cloud-backend
course_id: cb-c01
title: "Containerized solutions: ACR, ACI, and Container Apps"
level: foundational
grounded_on: "AZ-204 skills outline (2026-01-14), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-204
synthetic: true
order: 3
prereqs: [cb-c01-m02]
objectives:
  - Build and publish container images to Azure Container Registry
  - Run isolated workloads on Azure Container Instances
  - Design microservice solutions on Azure Container Apps
---

# Containerized solutions: ACR, ACI, and Container Apps

Northwind Parcel's tariff-calculation service has an awkward dependency: a specific version of a numerical library plus a system package that the App Service runtime image does not include. "It works on my machine" is exactly the failure mode containers were invented to kill. The team wants to ship the *whole environment* — code, runtime, and OS libraries — as one immutable artifact that runs identically on a laptop, in CI, and in production. That artifact is a container image, and Azure gives you three places to keep and run it: a private registry, a no-frills runner for one-off workloads, and a managed platform for long-lived microservices.

## Learning objectives

By the end of this module you will be able to:

- Build a container image and publish it to a private Azure Container Registry.
- Run a single isolated container on Azure Container Instances for short-lived or burst workloads.
- Deploy and configure a scalable microservice on Azure Container Apps.

## Concepts

### Images and Azure Container Registry

A container **image** is a layered, read-only bundle of your application and everything it needs to run; a **container** is a running instance of that image. You build an image from a `Dockerfile`, which is a recipe of layers. Because each layer is content-addressed, identical layers are cached and shared — change only your code and only that layer rebuilds. **Azure Container Registry (ACR)** is a private, managed registry where you store and version those images close to where they will run. Tagging discipline matters: a tag like `latest` is convenient but mutable, so production should pin an immutable tag (a version or a commit SHA) to guarantee you can redeploy exactly what you tested.

### Azure Container Instances: one container, no orchestrator

**Azure Container Instances (ACI)** runs a single container (or a small group) directly, without you managing any cluster or orchestration layer. You point it at an image, set CPU and memory, and it runs — billed for the duration it runs. ACI shines for short-lived or bursty work: a batch job, a build step, a one-off data migration, or overflow capacity. It is deliberately not the place for a complex, always-on microservice with autoscaling and traffic-splitting needs; for that you want something with an orchestration model.

### Azure Container Apps: serverless microservices

**Azure Container Apps** is a managed platform for running containerized services and microservices without operating Kubernetes yourself. It gives you what real services need: scaling driven by HTTP traffic or event sources (including scale-to-zero), revisions for safe rollout and traffic-splitting between versions, built-in ingress with TLS, and service-to-service discovery. The right way to think about the trio: ACR is *where the image lives*, ACI is *where you run a container quickly and simply*, and Container Apps is *where you run a service that must scale, roll out gradually, and stay up*.

## Walkthrough: containerizing the tariff service

Northwind Parcel packages the tariff service, pushes it to ACR, and runs it on Container Apps. Start with a minimal, correct `Dockerfile`:

```dockerfile
# Dockerfile for the tariff-calc service
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "tariff.app:app"]
```

Now build and publish. A convenient trick: `az acr build` runs the build *in the registry*, so you do not need Docker installed locally.

```bash
RG="northwind-parcel-rg"
ACR="northwindacr"          # registry name (becomes northwindacr.azurecr.io)

# 1. Create the private registry
az acr create --resource-group "$RG" --name "$ACR" --sku Basic

# 2. Build the image in ACR and tag it with an immutable version
az acr build --registry "$ACR" \
  --image tariff-calc:1.4.0 .
```

With the image in ACR, deploy it as a Container App. The environment is the shared boundary (networking, logging) that one or more container apps live in.

```bash
ENV="northwind-aca-env"
APP="tariff-calc"

# 3. Create a Container Apps environment
az containerapp env create \
  --name "$ENV" --resource-group "$RG" --location eastus

# 4. Deploy the image as an externally reachable app with autoscaling
az containerapp create \
  --name "$APP" --resource-group "$RG" \
  --environment "$ENV" \
  --image "$ACR.azurecr.io/tariff-calc:1.4.0" \
  --registry-server "$ACR.azurecr.io" \
  --target-port 8000 --ingress external \
  --min-replicas 0 --max-replicas 5
```

What to observe: `az acr build` produced an immutable `tariff-calc:1.4.0` image without local Docker. The Container App exposes the service on a managed HTTPS endpoint (`--ingress external`), and `--min-replicas 0` means it scales to zero when idle — like Functions, you stop paying for idle compute, at the cost of a cold start. To ship version `1.5.0`, you build a new tag and update the app, which creates a new revision you can route traffic to gradually. For a contrasting one-off job, the same image could instead run on ACI with `az container create` and exit when finished — no environment, no scaling rules, just a container that runs and stops.

## Common pitfalls

- **Deploying the `latest` tag to production.** `latest` is mutable, so "redeploy what we tested" becomes impossible. Pin an immutable tag (version or commit SHA) for anything you need to reproduce.
- **Reaching for ACI when you need a service.** ACI has no built-in autoscaling, revisions, or traffic-splitting. Using it for an always-on, scaling microservice means reinventing orchestration; use Container Apps instead.
- **Fat images that rebuild slowly.** Copying your whole source before installing dependencies busts the dependency cache on every code change. Copy and install dependencies first, then copy code, so the expensive layer is cached.
- **Forgetting registry authentication on deploy.** A Container App pulling from a private ACR needs credentials or a managed identity with pull rights. Omitting `--registry-server` (or identity config) yields image-pull failures.
- **Ignoring scale-to-zero cold starts for latency-critical apps.** `--min-replicas 0` saves money but adds startup latency on the first request. For user-facing paths that must respond instantly, set a minimum replica count above zero.

## Knowledge check

1. You need to run a one-time database migration that takes ten minutes and then exits. Which of the three services fits best, and why not Container Apps?
2. Why should a production deployment reference `tariff-calc:1.4.0` rather than `tariff-calc:latest`?
3. Your `Dockerfile` copies all source code before running `pip install`. Why does this slow down rebuilds, and how do you fix it?

<details>
<summary>Answers</summary>

1. Azure Container Instances — it runs a single container for its duration and exits, with no orchestration overhead. Container Apps is built for long-lived, scaling services and is heavier than a one-off job needs. — Match the service to workload lifecycle: transient task → ACI; persistent scaling service → Container Apps.
2. `latest` is a mutable tag, so the image it points to can change; an immutable version tag guarantees you redeploy the exact bits you tested. — Reproducible deploys require immutable references.
3. Copying source first invalidates the dependency-install layer's cache on every code change, forcing a full reinstall. Copy `requirements.txt` and install dependencies before copying the rest of the code. — Order layers from least- to most-frequently-changed to maximize cache hits.

</details>

## Summary

Containers package your code, runtime, and OS dependencies into one immutable image that runs the same everywhere. Azure Container Registry is the private home for those images, Azure Container Instances runs a single container quickly for short-lived or bursty work, and Azure Container Apps runs scalable, long-lived microservices with revisions, ingress, and event-driven scaling — without you operating Kubernetes. Choose by workload lifecycle and scaling needs. The final module ties the course together: making any of these compute services scale to demand, configuring diagnostics so you can see what they are doing, and choosing the right service deliberately.

## Further learning

- [Introduction to Azure Container Registry](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-intro)
- [What is Azure Container Instances?](https://learn.microsoft.com/en-us/azure/container-instances/container-instances-overview)
- [Azure Container Apps overview](https://learn.microsoft.com/en-us/azure/container-apps/overview)
- [Build and push an image with az acr build](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-tutorial-quick-task)
