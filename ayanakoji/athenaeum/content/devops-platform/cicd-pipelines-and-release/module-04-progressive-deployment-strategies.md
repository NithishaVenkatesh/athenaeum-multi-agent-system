---
kind: module
id: do-c02-m04
vertical: devops-platform
course_id: do-c02
title: Progressive deployment strategies
level: intermediate
grounded_on: "AZ-400 skills outline (2026-04-24), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-400
synthetic: true
order: 4
prereqs: [do-c02-m03]
objectives:
  - Design blue-green, canary, and ring deployments
  - Minimize downtime with deployment slots and rolling deployments
  - Implement feature flags with Azure App Configuration
---

# Progressive deployment strategies

Larkspur Robotics now has a pipeline that builds, versions, tests, and gates — and yet the last release still hurt. The change passed every gate, deployed to all production servers at once, and a subtle bug in the `fleet-service` route planner sent every robot the wrong waypoint for eleven minutes before anyone rolled back. The tests were not wrong; production is just bigger and stranger than any test environment. The skill you need now is the one that accepts this truth: assume a change *might* be bad, and arrange the release so that when it is, only a sliver of users feel it and recovery is instant. That is progressive delivery.

## Learning objectives

By the end of this module you will be able to:

- Design blue-green, canary, and ring deployment strategies and choose the right one for a given risk profile.
- Minimize downtime during releases using deployment slots with swap and rolling deployments behind a load balancer.
- Decouple deploy from release with feature flags backed by Azure App Configuration's Feature Manager.

## Concepts

### Blue-green, canary, and rings: three ways to shrink blast radius

These strategies all answer one question — *how much of production sees the new version, and how fast can I undo it?* — with different trade-offs.

**Blue-green** runs two identical production environments. "Blue" is live; you deploy the new version to the idle "green", warm it, smoke-test it, then flip all traffic from blue to green at once. The win is a near-instant rollback: if green misbehaves, flip back to blue, which is still running the old version. The cost is running two full environments and the fact that the cutover is all-or-nothing — everyone moves together, so a bug that smoke tests miss still hits everyone, just reversibly.

**Canary** releases to a small percentage of real traffic first — say 5% — while watching error rates and latency. If the canary stays healthy, you widen to 25%, then 100%; if it degrades, you halt and roll back having exposed only a fraction of users. Canary trades the instant-flip simplicity of blue-green for a smaller initial blast radius and requires good telemetry to judge "healthy."

**Ring deployment** (progressive exposure) generalizes canary to *audiences*: ring 0 is internal staff, ring 1 is opt-in early adopters, ring 2 is everyone. You promote ring by ring, gaining confidence with each. Rings suit changes where the risk is about real-world usage diversity rather than raw load.

### Slots and rolling deployments: minimizing downtime

A **deployment slot** (on Azure App Service) is a live staging environment that shares the app's infrastructure but has its own URL. You deploy to the slot, let the app fully start and warm its caches, then perform a **swap**, which exchanges the slot's running instances with production's — a routing change, not a redeploy. Because the new code was already warm before the swap, users do not hit a cold start, which is what makes slot swap an effective low-downtime technique and, in practice, a lightweight blue-green.

A **rolling deployment** updates instances behind a load balancer in batches: take a few instances out of rotation, update them, return them, repeat. At every moment some instances serve the old version and some the new, so capacity stays up and there is no full outage — at the cost of a window where both versions run at once, which your change must tolerate (especially for database schema changes).

### Feature flags: separating deploy from release

The most powerful idea here is that **deploying code and releasing a feature are different events.** A **feature flag** is a runtime switch: you ship the new route-planner code to production *disabled*, behind a flag, then turn it on for a chosen audience without another deployment — and turn it off instantly if it misbehaves, again without a deployment. **Azure App Configuration's Feature Manager** centralizes these flags so they are managed outside your code and can target audiences (a percentage of users, a named group) from one place. Flags compose beautifully with the strategies above: a canary becomes "enable the flag for 5% of users," and rollback becomes "set the flag to off" — a configuration change measured in seconds, not a redeploy.

## Walkthrough: shipping the route planner behind a flag and a slot

Larkspur will ship the rewritten route planner safely. The code reads a feature flag from App Configuration and only uses the new algorithm when the flag is on; deployment goes to a slot and swaps. First, the application reads the flag (C#, using the Feature Management library wired to App Configuration):

```csharp
// Program.cs — wire App Configuration + Feature Management
var builder = WebApplication.CreateBuilder(args);

builder.Configuration.AddAzureAppConfiguration(options =>
{
    options.Connect(new Uri(builder.Configuration["AppConfig:Endpoint"]!),
                    new DefaultAzureCredential())
           .UseFeatureFlags();   // pull feature flags from App Configuration
});
builder.Services.AddFeatureManagement();

var app = builder.Build();
app.Run();
```

```csharp
// RoutePlannerService.cs — branch on the flag at runtime
public class RoutePlannerService(IFeatureManager features)
{
    public async Task<Route> PlanAsync(Fleet fleet)
    {
        // Deploy disabled; release by flipping the flag — no redeploy needed.
        if (await features.IsEnabledAsync("NewRoutePlanner"))
            return PlanWithNewAlgorithm(fleet);

        return PlanWithLegacyAlgorithm(fleet);
    }
}
```

Authentication uses `DefaultAzureCredential`, so no connection secret lives in code — it resolves a managed identity in Azure and your developer credentials locally. The pipeline deploys to a slot and swaps, so the new build is warm before it takes traffic:

```yaml
  - stage: DeployProduction
    jobs:
      - deployment: deploy_fleet
        environment: production
        pool: { vmImage: 'ubuntu-latest' }
        strategy:
          runOnce:
            deploy:
              steps:
                # Deploy to the 'staging' slot, not production directly
                - task: AzureWebApp@1
                  inputs:
                    appName: 'larkspur-fleet-service'
                    deployToSlotOrASE: true
                    slotName: 'staging'
                # Warm-up time happens here; then swap slot into production
                - task: AzureAppServiceManage@0
                  inputs:
                    action: 'Swap Slots'
                    webAppName: 'larkspur-fleet-service'
                    sourceSlot: 'staging'
```

The release now has two independent safety layers. The slot swap means users never see a cold start and a bad swap can be swapped back. The feature flag means even after the code is live everywhere, the *new behavior* is off until Larkspur enables `NewRoutePlanner` for ring 0 (internal robots in the test warehouse), watches telemetry, then widens the percentage — and can kill it in seconds if waypoints go wrong, with no deployment at all. The exact task names, slot-warmup behavior, and Feature Manager targeting filters evolve, so verify current task versions and the App Configuration SDK surface in the docs.

## Common pitfalls

- **All-at-once deploys with no rollback plan.** Pushing to 100% of production simultaneously means every user hits a bad change and recovery requires a fresh deploy. Use a strategy that exposes gradually and can revert by routing or flag.
- **Canary without telemetry.** A canary you cannot measure is just a slow full rollout. You must watch error rate and latency on the canary slice and define in advance what "unhealthy" means and what halts the rollout.
- **Forgetting backward compatibility during rolling/canary windows.** While both versions run together, a schema change that the old version cannot read will break it. Make schema changes additive and backward-compatible, deploying them ahead of the code that requires them.
- **Letting feature flags become permanent technical debt.** Flags left in the code forever multiply branches and confuse everyone. Treat each flag as temporary: once a feature is fully rolled out and stable, remove the flag and the dead branch.
- **Swapping a cold slot.** Swapping before the new instances are warmed up reintroduces the cold-start latency the slot was meant to avoid. Warm the slot (and let dependent connections initialize) before the swap.

## Knowledge check

1. You must ship a high-risk change and want both a small initial blast radius *and* the ability to disable the new behavior in seconds without redeploying. Which two techniques combine to give you that, and what does each contribute?
2. During a rolling deployment, a small percentage of requests start failing intermittently and the errors disappear once the rollout completes. What class of bug does this most likely indicate?
3. Why is a deployment slot swap often described as a lightweight blue-green deployment, and what specifically prevents users from experiencing a cold start during it?

<details>
<summary>Answers</summary>

1. Canary (or ring) exposure plus a feature flag. Canary limits how many users see the change at first; the flag lets you disable the new behavior instantly via configuration rather than a redeploy. — Progressive exposure shrinks blast radius; flags decouple release from deploy.
2. A backward-compatibility problem between the two versions running simultaneously — for example, a non-additive schema or contract change the old version cannot handle. Once all instances run the new version, the conflict disappears. — Mixed-version windows expose incompatible changes.
3. Both slot and production run full environments and you flip traffic between them, like blue-green. The new code is fully started and warmed in the slot *before* the swap, so the swap is a routing change to already-warm instances rather than a cold start. — Pre-warming is what makes the swap low-downtime.

</details>

## Summary

Progressive delivery assumes any change might be bad and arranges the release so failures stay small and reversible: blue-green gives instant flip-back, canary and rings shrink the initial audience, slots and rolling deployments remove downtime, and feature flags separate deploying code from releasing behavior so you can enable and disable features in seconds. Layering a slot swap with an App Configuration feature flag, Larkspur can ship the route planner to a sliver of robots, watch, widen, and kill it instantly if needed. With this module you complete the arc of **CI/CD Pipelines & Release Engineering** — from pipelines as code, through versioned artifacts and gated quality, to releases that fail small.

## Further learning

- [Set up staging environments with deployment slots in App Service](https://learn.microsoft.com/en-us/azure/app-service/deploy-staging-slots)
- [Manage feature flags with Azure App Configuration](https://learn.microsoft.com/en-us/azure/azure-app-configuration/manage-feature-flags)
- [Use feature flags in an ASP.NET Core app](https://learn.microsoft.com/en-us/azure/azure-app-configuration/use-feature-flags-dotnet-core)
- [Deployment jobs and strategies in Azure Pipelines](https://learn.microsoft.com/en-us/azure/devops/pipelines/process/deployment-jobs)
