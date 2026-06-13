---
kind: module
id: as-c02-m02
vertical: architecture-security
course_id: as-c02
title: Designing governance
level: intermediate
grounded_on: "AZ-305 skills outline (2026-04-17), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-305
synthetic: true
order: 2
prereqs: [as-c02-m01]
objectives:
  - Recommend a structure for management groups, subscriptions, and resource groups
  - Design a resource tagging strategy that supports cost allocation and operations
  - Recommend solutions for managing compliance and identity governance with Azure Policy
---

# Designing governance

Helios Renewables, a fictional clean-energy company, started with one Azure subscription and a handful of engineers. Three years later it has forty subscriptions, six business units, two regulatory regimes, and nobody who can answer the question "which resources are non-compliant and who pays for them?" Bills arrive with no way to attribute cost. A developer spun up a database in a region the company's data-residency policy forbids, and nobody noticed for a month. This is governance debt, and it is far cheaper to design upfront than to retrofit. This module teaches you to design the structures and guardrails that keep a large Azure estate consistent, attributable, and compliant — without a human approving every resource.

## Learning objectives

By the end of this module you will be able to:

- Recommend a structure for management groups, subscriptions, and resource groups for an organization.
- Design a resource tagging strategy that supports cost allocation, ownership, and operations.
- Recommend a compliance solution using Azure Policy, initiatives, and the regulatory compliance dashboard.
- Recommend an identity-governance solution using access reviews and entitlement management.

## Concepts

### The resource hierarchy: management groups, subscriptions, resource groups

Azure organizes resources in a hierarchy, and good governance starts with using it deliberately. At the top sit **management groups**, which form a tree (under a single root) and exist to apply policy and access *above* the subscription level. Beneath them are **subscriptions**, which are the primary unit of billing, the boundary for many quotas, and a natural blast-radius boundary. Within a subscription, **resource groups** hold resources that share a lifecycle.

The architectural decision is how to shape the management-group tree. Two common patterns: organize by *business unit* (a management group per division) or by *environment and workload type*. Microsoft's Cloud Adoption Framework landing-zone model suggests a hybrid: top-level groups separating platform resources (shared networking, identity, management) from application landing zones, with further separation for sandbox and decommissioned subscriptions. The point is not to copy a diagram but to recognize that *policy and RBAC are inherited down this tree*, so the shape determines where you can enforce a control once and have it apply everywhere below.

A practical guideline: assign policy and broad RBAC at the management-group level so it is inherited, and reserve subscriptions for billing and isolation boundaries rather than for fine-grained control. Avoid an overly deep tree — every extra level is cognitive overhead with little benefit beyond a few layers.

### Tagging: making the estate legible

A **tag** is a key-value pair attached to a resource (or resource group, or subscription). Tags carry no permissions, but they are the connective metadata that makes cost management, operations, and automation possible. A tag like `costCenter = renewables-grid` lets finance attribute spend; `owner = team-grid@helios.example` tells an on-call engineer who to page; `environment = prod` lets you filter dashboards and target automation.

A tagging strategy is a *governance artifact*, not an afterthought. Decide a small, mandatory set of tags, document allowed values, and — critically — *enforce* them, because tags applied by convention alone decay immediately. Note that tags are not automatically inherited by child resources from a resource group; you enforce or copy them with Azure Policy. Keep the mandatory set short (cost center, owner, environment, data classification is a reasonable starting point); a sprawling tag taxonomy that nobody maintains is worse than a small one that is enforced.

### Azure Policy: guardrails instead of gatekeepers

**Azure Policy** evaluates resources against rules and takes an *effect*. The effects are the heart of the design. `audit` records non-compliance without blocking — useful for measuring before enforcing. `deny` rejects a non-compliant resource at creation time — the hard guardrail that would have stopped Helios's forbidden-region database. `deployIfNotExists` and `modify` are *remediation* effects that deploy a missing resource (say, a diagnostic setting) or add a missing tag automatically. Grouping related policies into an **initiative** (policy set) lets you assign a coherent bundle — for example, a regulatory baseline — as one unit and report compliance against it.

This is the shift from gatekeeping to guardrails: instead of a human reviewing every deployment, you encode the rules once and let the platform enforce them continuously, surfacing a compliance score you can track. For identity governance specifically, **access reviews** periodically force owners to re-certify who still needs access (catching Meridian's expired contractors from the previous module), and **entitlement management** packages roles and resources into access packages that users can request with built-in approval and expiry.

## Walkthrough: enforcing region and tagging at Helios

Helios's data-residency policy says production workloads may only be deployed in two approved regions, and every resource must carry an `owner` tag. You will enforce both with Azure Policy at the management-group level so the controls apply to every subscription beneath it. Here is the allowed-locations policy assignment expressed with the `az` CLI, using a built-in policy definition:

```bash
# Restrict resource locations to approved regions across the Helios platform MG.
MG_ID="/providers/Microsoft.Management/managementGroups/helios-platform"

# Built-in definition: "Allowed locations" (audits/denies disallowed regions).
ALLOWED_LOCATIONS_DEF="/providers/Microsoft.Authorization/policyDefinitions/e56962a6-4747-49cd-b67b-bf8b01975c4c"

az policy assignment create \
  --name "allowed-locations-prod" \
  --display-name "Helios: restrict resource locations" \
  --scope "$MG_ID" \
  --policy "$ALLOWED_LOCATIONS_DEF" \
  --params '{ "listOfAllowedLocations": { "value": ["westeurope", "northeurope"] } }' \
  --enforcement-mode Default   # Default enforces (deny); DoNotEnforce only audits
```

The `--scope` pointing at the management group is what gives this leverage: assigning once at `helios-platform` means every current and future subscription under it inherits the restriction — you do not touch the forty subscriptions individually. The `--enforcement-mode Default` makes the effect active so a deployment to a disallowed region is blocked; setting it to `DoNotEnforce` would let you measure impact first. For the tagging requirement you would assign a second policy using the `modify` effect to add a default `owner` tag, or `deny` to reject untagged resources, and bundle both into an initiative so compliance reports as a single number. After assignment, the compliance dashboard shows which existing resources are non-compliant, and a remediation task can bring them into line.

## Common pitfalls

- **Deep, business-unit-mirroring management-group trees.** A tree that copies the org chart looks tidy but breaks every reorganization and adds layers that carry no controls. Shape the tree around where you actually need to inherit policy and access.
- **Tagging by convention without enforcement.** Tags that rely on people remembering decay within weeks and then can't be trusted for cost allocation. Enforce the mandatory set with policy, and keep the set small.
- **Jumping straight to `deny`.** Turning on hard enforcement across an existing estate can block legitimate work and trigger a flood of failures. Start with `audit`, measure, communicate, then move to `deny`.
- **Assigning policy at the subscription instead of the management group.** You then have to repeat the assignment for every new subscription. Assign at the highest scope where the control should apply and let inheritance do the work.
- **Forgetting that remediation effects need a managed identity.** `deployIfNotExists` and `modify` policies act on your behalf and require a managed identity with sufficient rights, or remediation silently fails — verify the required role assignments in the docs when designing them.

## Knowledge check

1. Helios wants a data-residency rule to apply automatically to every subscription it creates in the future, without manual steps. At what scope do you assign the policy, and why does this satisfy the requirement?
2. The finance team cannot attribute cloud spend to business units. Which governance mechanism addresses this, and what makes it reliable enough to trust?
3. You need to roll out a strict "production resources must use private networking" rule across an estate that currently violates it widely. What policy effect do you start with, and what is the migration path to full enforcement?

<details>
<summary>Answers</summary>

1. At the `helios-platform` management group — policy is inherited down the hierarchy, so every existing and future subscription beneath the group is automatically subject to it without per-subscription work.
2. A tagging strategy (for example a mandatory `costCenter` tag) enforced by Azure Policy — enforcement is what makes tags reliable, since convention-only tags decay and can't be trusted for cost allocation.
3. Start with the `audit` effect to measure the scale of non-compliance without breaking workloads, communicate and remediate, then switch the assignment to `deny` once the estate is clean — a measure-then-enforce migration.

</details>

## Summary

Governance is the discipline that keeps a growing Azure estate consistent, attributable, and compliant without a human approving every action. Shape the management-group hierarchy around where you need to inherit policy and access, enforce a small mandatory tag set, and use Azure Policy initiatives — auditing first, then denying — to turn rules into automatic guardrails, complemented by access reviews and entitlement management for identity governance. With the estate under control, the next module makes it observable: **Designing logging and monitoring**.

## Further learning

- [Organize your Azure resources effectively with management groups](https://learn.microsoft.com/en-us/azure/governance/management-groups/overview)
- [What is Azure Policy?](https://learn.microsoft.com/en-us/azure/governance/policy/overview)
- [Use tags to organize your Azure resources and management hierarchy](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/tag-resources)
- [What are access reviews?](https://learn.microsoft.com/en-us/entra/id-governance/access-reviews-overview)
