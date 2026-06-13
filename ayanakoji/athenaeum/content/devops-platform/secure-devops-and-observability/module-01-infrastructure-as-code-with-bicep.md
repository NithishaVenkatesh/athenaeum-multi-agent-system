---
kind: module
id: do-c03-m01
vertical: devops-platform
course_id: do-c03
title: Infrastructure as code with Bicep
level: advanced
grounded_on: "AZ-400 skills outline (2026-04-24), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-400
synthetic: true
order: 1
prereqs: [do-c02]
objectives:
  - Define an IaC strategy anchored in source control and automated deployment testing
  - Author Bicep modules that deploy repeatable environments idempotently
  - Implement desired-state configuration so environments converge to the declared spec
---

# Infrastructure as code with Bicep

The staging environment for Meridian Freight's booking API was built eighteen months ago by an engineer who has since left. Nobody is certain which app settings it carries, whether its storage account allows public blob access, or why production behaves differently. Rebuilding it from the portal would take a careful afternoon and still not match. This is the cost of click-built infrastructure: it is not reviewable, not reproducible, and not trustworthy. When you can express an environment as a file that lives beside your application code, every one of those problems dissolves — the environment becomes something you can diff, review, test, and recreate on demand.

## Learning objectives

By the end of this module you will be able to:

- Define an infrastructure-as-code strategy anchored in source control with automated deployment testing.
- Author Bicep modules that deploy repeatable, parameterized environments idempotently.
- Implement desired-state configuration so an environment converges to its declared specification.
- Validate a deployment with what-if analysis before applying changes.

## Concepts

### Declarative infrastructure and idempotency

Bicep is a declarative language: you describe the *end state* you want — a resource group containing a storage account with these properties, a Key Vault with that access model — and the deployment engine works out the operations needed to reach it. This is fundamentally different from a script that runs `az storage account create`. A script is imperative; run it twice and it may error because the resource already exists. A Bicep deployment is *idempotent*: applying the same template against the same target repeatedly converges on the same state without harm. The engine compares declared state against actual state and reconciles the difference.

Under the hood, Bicep compiles to an Azure Resource Manager (ARM) JSON template and is submitted as a deployment to a scope — a resource group, subscription, management group, or tenant. ARM then orders the operations, respecting dependencies you express implicitly by referencing one resource's properties from another. You almost never need explicit `dependsOn` clauses; referencing `storageAccount.id` from another resource tells ARM the ordering for free.

### Modules, parameters, and environment promotion

A single monolithic template becomes unmaintainable quickly. Bicep *modules* let you factor a deployment into composable units — a networking module, a storage module, an app module — each with its own parameters and outputs. The root template wires them together. This is the same decomposition discipline you apply to application code, and it pays off the same way: you test and reason about small units.

The lever that turns one template into many environments is *parameterization*. The same Bicep file deploys dev, staging, and production; what differs is the parameter values you supply — SKU sizes, instance counts, naming prefixes. Keep those values in per-environment parameter files (`.bicepparam`) under source control. Promotion between environments then means deploying the *identical* template with a different parameter file, which is exactly what makes staging a faithful rehearsal for production.

### Desired-state configuration and drift

Declaring state is only half the value; the other half is *keeping* the live environment matching the declaration. When someone changes a setting in the portal, the environment has *drifted* from its source-of-truth template. A mature IaC strategy treats the template as authoritative and re-deploys regularly — often from the pipeline on every merge to the main branch — so drift is corrected automatically rather than accumulating into the Meridian staging mystery.

Before you apply a change, you want to know what it will do. The `what-if` operation previews the create, modify, and delete actions a deployment would perform, without performing them. Wiring a what-if step into a pull-request pipeline turns infrastructure changes into reviewable diffs: a reviewer sees that this PR will, say, add a diagnostic setting and resize one plan, and nothing else.

## Walkthrough: declaring Meridian Freight's API environment

Meridian's platform team wants a reproducible environment for the booking API: a storage account for queues and a Linux App Service plan plus web app, all deployable per environment from one template. You will author the Bicep, validate it, and deploy it.

```bicep
// main.bicep — deploys at resource group scope
@description('Short environment name, e.g. dev or prod')
@allowed(['dev', 'staging', 'prod'])
param environmentName string

@description('Azure region for all resources')
param location string = resourceGroup().location

// Deterministic, environment-scoped naming
var namePrefix = 'meridian-booking-${environmentName}'
var storageName = toLower(replace('mrdnbook${environmentName}${uniqueString(resourceGroup().id)}', '-', ''))

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: take(storageName, 24)
  location: location
  sku: {
    name: environmentName == 'prod' ? 'Standard_GRS' : 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
  }
}

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: '${namePrefix}-plan'
  location: location
  sku: {
    name: environmentName == 'prod' ? 'P1v3' : 'B1'
  }
  kind: 'linux'
  properties: {
    reserved: true // required for Linux plans
  }
}

resource site 'Microsoft.Web/sites@2023-12-01' = {
  name: '${namePrefix}-api'
  location: location
  properties: {
    serverFarmId: plan.id // implicit dependency on the plan
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'DOTNETCORE|8.0'
      minTlsVersion: '1.2'
    }
  }
}

output apiHostName string = site.properties.defaultHostName
```

Save a parameter file `staging.bicepparam` next to it:

```bicep
using './main.bicep'
param environmentName = 'staging'
```

Now preview and deploy from the CLI. The what-if run shows exactly what will change before anything is touched:

```bash
# Preview the change set — review this output in a PR before applying
az deployment group what-if \
  --resource-group rg-meridian-staging \
  --template-file main.bicep \
  --parameters staging.bicepparam

# Apply once the preview looks right
az deployment group create \
  --resource-group rg-meridian-staging \
  --template-file main.bicep \
  --parameters staging.bicepparam
```

Run the `create` command a second time and observe that ARM reports no changes: the deployment is idempotent. Switch the parameter file to `prod.bicepparam` and the same template stands up a production environment with geo-redundant storage and a production-grade plan — the only difference is data, not code. Note that the specific API versions and SKU names above evolve; treat them as a current example and verify the latest in the docs for your subscription.

## Common pitfalls

- **Hardcoding names and regions.** Literal resource names collide across environments and globally (storage accounts need a globally unique name). Derive names from a prefix plus `uniqueString()` and pass region as a parameter.
- **Reaching for `dependsOn` reflexively.** Explicit dependencies that duplicate an implicit reference add noise and can mask ordering bugs. Let ARM infer ordering from property references; use `dependsOn` only when no reference exists.
- **Skipping what-if.** Deploying straight to a shared environment without previewing the change set is how an innocent edit silently deletes a resource. Make what-if a required step on infrastructure pull requests.
- **Treating the portal as a second source of truth.** Any change made outside the template is drift waiting to be silently reverted on the next deploy — or worse, never reconciled. Decide the template is authoritative and route all changes through it.
- **One giant template.** A 900-line `main.bicep` is as unmaintainable as a 900-line function. Factor cohesive resources into modules with clear parameters and outputs.

## Knowledge check

1. Your teammate worries that re-running the staging deployment on every merge will recreate the storage account and wipe its data. Are they right, and why?
2. A reviewer asks how they can be sure a Bicep pull request will not delete the production database. What pipeline step answers that, and what does it show?
3. Why is it preferable to deploy the *same* Bicep template to staging and production rather than maintaining a separate template per environment?

<details>
<summary>Answers</summary>

1. No. Bicep deployments are idempotent — ARM reconciles declared state against actual state, so an unchanged storage account is left as-is rather than recreated. Data is preserved unless the template itself removes the resource. — Idempotency means repeated application converges on the same state without destructive churn.
2. A `what-if` step. It previews the create, modify, and delete operations the deployment would perform without executing them, so a reviewer can confirm no delete touches the database. — What-if turns infrastructure changes into a reviewable diff before they are applied.
3. Using one parameterized template guarantees staging is structurally identical to production, differing only in parameter values, so staging is a faithful rehearsal; divergent templates drift apart and let environment-specific bugs hide. — Promotion should change data (parameters), not code (the template).

</details>

## Summary

Infrastructure as code turns environments into reviewable, reproducible artifacts: Bicep declares the end state, ARM reconciles it idempotently, modules and parameters let one template serve every environment, and what-if makes changes safe to review. Treating the template as the single source of truth keeps drift from accumulating. With environments now defined as code, the next module tackles the credentials those environments need — storing secrets in Key Vault and, better, eliminating stored secrets entirely with workload identity federation.

## Further learning

- [What is Bicep?](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/overview)
- [Preview Azure deployment changes by using what-if](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deploy-what-if)
- [Bicep parameter files](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/parameter-files)
- [Deploy Bicep files with Azure CLI](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deploy-cli)
