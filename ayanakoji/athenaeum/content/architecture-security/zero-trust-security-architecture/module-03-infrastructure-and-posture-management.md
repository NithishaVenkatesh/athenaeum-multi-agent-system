---
kind: module
id: as-c03-m03
vertical: architecture-security
course_id: as-c03
title: Infrastructure and posture management
level: advanced
grounded_on: "SC-100 skills outline (2026-04-27), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/sc-100
synthetic: true
order: 3
prereqs: [as-c03-m01]
objectives:
  - Evaluate posture with Defender for Cloud and Secure Score
  - Design posture management across hybrid/multicloud
  - Specify requirements for securing endpoints and services
---

# Infrastructure and posture management

Meridian Harbour's two acquired carriers did not run only in Azure. One ran a fleet of VMs in AWS; the other kept a rack of on-premises servers in a depot and a small Kubernetes cluster running a route-optimization service. Detection from the previous module tells you when something goes wrong, but it does not tell you that the AWS storage buckets are public, the on-premises servers are missing patches, or the Kubernetes cluster lets any pod talk to any other. Those are *posture* problems — the standing weaknesses an attacker looks for before they ever launch an attack. This module teaches you to see and raise security posture across a hybrid, multicloud estate, so you shrink the attack surface instead of only reacting to it.

## Learning objectives

By the end of this module you will be able to:

- Evaluate security posture using Microsoft Defender for Cloud and the MCSB.
- Interpret and improve Microsoft Secure Score to prioritize remediation.
- Design posture management across hybrid and multicloud using Azure Arc.
- Specify security requirements for containers and container orchestration.

## Concepts

### Posture management: find weakness before the attacker does

Posture management is the continuous assessment of your resources against a set of security best practices, surfacing misconfigurations as prioritized recommendations. **Microsoft Defender for Cloud** is the posture engine: it continuously evaluates connected resources, and its free foundational layer (Cloud Security Posture Management) assesses them against the **MCSB** — the same benchmark you mapped your strategy to in module one. That alignment is deliberate: the controls you committed to are the controls Defender for Cloud measures, so your assessment and your strategy speak the same language.

The output is a stream of recommendations — "storage account allows public access," "VM is missing endpoint protection" — each tied to a control and a severity. This is the assume-breach principle applied *before* the breach: you are minimizing the footholds an attacker could use.

### Secure Score turns posture into a number you can manage

A list of hundreds of recommendations is paralysis. **Microsoft Secure Score** condenses your Defender for Cloud posture into a single percentage and, crucially, weights recommendations by impact so you know what to fix first. Each recommendation is grouped into a security control with a potential point gain, so you can answer "what is the single most valuable thing to remediate this sprint?" Secure Score is a *management* tool: you baseline it, set an improvement target per phase (your RaMP had this as a Phase 3 metric), and track the trend. Treat a one-time score as meaningless and the trend as the truth — posture decays as people deploy new resources, so a flat or rising score under growth is the real win.

### Hybrid and multicloud: extend the control plane with Azure Arc

Defender for Cloud assesses Azure resources natively, but Meridian Harbour's estate is not all Azure. **Azure Arc** projects non-Azure resources — on-premises servers, the depot VMs, even other clouds' machines and Kubernetes clusters — into Azure's control plane as first-class resources. Once a server is Arc-enabled, you can apply Azure Policy to it, onboard it to Defender for Cloud, and assess its posture exactly as you would an Azure VM. For other clouds, Defender for Cloud also connects directly to AWS and GCP accounts to assess their native resources against equivalent benchmarks. The architectural goal: *one* posture view and *one* policy plane across everything, instead of a separate security story per environment. Without that, every acquisition adds another blind spot.

### Containers and orchestration: posture for a moving target

Containers change fast and run in shared clusters, which creates failure modes VMs do not have. A complete container security design spans the whole lifecycle: scan images for vulnerabilities *before* they reach a registry, enforce that only trusted images run, harden the orchestrator (control-plane access, RBAC, and network policy so pods cannot freely reach each other), and protect the running cluster at runtime. Defender for Cloud's container plan assesses Kubernetes configuration and registry images and detects runtime threats. The principle is the same as everywhere else — least privilege and assume breach — applied to a target that redeploys hourly, so you enforce it as policy in the pipeline and the cluster rather than as a one-time review.

## Walkthrough: a single posture view for Meridian Harbour

You will onboard the depot's on-premises servers into Azure's control plane so they appear in Defender for Cloud, then query posture organization-wide. First, Arc-enable an on-premises server. On the server, you run the connection command (this also installs the Connected Machine agent).

```bash
# Run on the depot's on-prem server to project it into Azure via Arc.
# Service principal values come from your onboarding setup; never hardcode secrets in scripts.
azcmagent connect \
  --service-principal-id "$ARC_SP_ID" \
  --service-principal-secret "$ARC_SP_SECRET" \
  --resource-group "rg-meridian-arc" \
  --tenant-id "$TENANT_ID" \
  --subscription-id "$SUBSCRIPTION_ID" \
  --location "eastus" \
  --tags "owner=depot-ops,env=onprem"
```

After this, the server shows up as a `Microsoft.HybridCompute/machines` resource. You enable the Defender for Cloud servers plan on the subscription so the Arc-connected machine is assessed against the MCSB just like a native VM. Now ask the genuinely hard question — "across our entire estate, what is unhealthy?" — with a single Azure Resource Graph query that spans Azure and Arc resources alike.

```kql
// Azure Resource Graph: unhealthy Defender for Cloud assessments across the estate
// (Defender for Cloud assessment schema evolves — verify table/field names in docs.)
securityresources
| where type == "microsoft.security/assessments"
| extend status = tostring(properties.status.code),
         severity = tostring(properties.metadata.severity),
         resourceId = tostring(properties.resourceDetails.id)
| where status == "Unhealthy"
| summarize findings = count() by severity, assessment = tostring(properties.displayName)
| order by findings desc
```

Because Arc made the on-premises servers Azure resources, this one query returns findings for cloud *and* depot machines together — the single posture view that was impossible when each environment had its own console. You would then sort by severity, pick the top Secure Score contributor, and remediate it as the sprint's posture work.

## Common pitfalls

- **Chasing every recommendation equally** — Remediating low-impact findings while a high-severity one lingers wastes the team. Let Secure Score's weighting drive priority; fix the highest point-value control first.
- **Reading Secure Score as a one-time grade** — A snapshot says nothing; posture decays as new resources deploy. Baseline it and manage the *trend* under growth.
- **Leaving non-Azure resources outside the control plane** — If the AWS account and on-premises servers are not connected via Arc/cloud connectors, they are invisible to your posture view and become the soft target. Onboard everything.
- **Securing containers only at runtime** — Catching a malicious image after it runs is too late. Shift left: scan images in the pipeline, enforce trusted-registry admission, and apply network policy in the cluster.
- **Assuming Defender for Cloud's free tier is enough everywhere** — Foundational CSPM assesses configuration, but workload threat protection (servers, containers, databases) requires the paid plans. Decide per workload which protection you need and verify which features the enabled plan covers.

## Knowledge check

1. Two recommendations are open: "MFA missing on some accounts" (high severity, large Secure Score gain) and "enable diagnostic logging on a test storage account" (low). The team has time for one this sprint. Which, and why is Secure Score the right arbiter?
2. The AWS-hosted VMs from one acquired carrier never appear in your posture dashboards. What is the most likely architectural cause and the fix?
3. Why is image scanning in the build pipeline considered part of *container security posture*, not just CI hygiene?

<details>
<summary>Answers</summary>

1. Fix the MFA gap — Secure Score weights recommendations by security impact and point value, so the high-severity, high-gain item reduces real risk most; it is the right arbiter because it encodes impact rather than treating all findings as equal. — Posture work should follow weighted impact, not count.
2. The AWS environment is not connected to Defender for Cloud (no AWS connector / not Arc-enabled), so its resources are outside the assessed control plane. Connect the AWS account via the multicloud connector to bring those VMs into a single posture view. — Unconnected environments are invisible blind spots.
3. A vulnerable image is a standing weakness the moment it could be deployed; catching it pre-registry prevents the misconfiguration from ever reaching runtime, which is exactly what posture management does — minimize footholds before attack. — Container posture spans the whole lifecycle, not just runtime.

</details>

## Summary

Posture management is how you shrink the attack surface before anyone attacks it: Defender for Cloud continuously assesses resources against the MCSB, Secure Score weights the findings so you remediate the highest-impact gaps first and manage the trend, and Azure Arc plus cloud connectors extend that single assessment plane across on-premises and other clouds so nothing is invisible. Containers get the same least-privilege, assume-breach treatment applied across their fast-moving lifecycle. With the infrastructure surface measured and hardened, the final module secures the layers closest to the attacker's prize — the applications and the data themselves.

## Further learning

- [Microsoft Defender for Cloud documentation](https://learn.microsoft.com/en-us/azure/defender-for-cloud/defender-for-cloud-introduction)
- [Security posture management and Secure Score in Defender for Cloud](https://learn.microsoft.com/en-us/azure/defender-for-cloud/secure-score-security-controls)
- [Azure Arc overview](https://learn.microsoft.com/en-us/azure/azure-arc/overview)
- [Container security with Microsoft Defender for Cloud](https://learn.microsoft.com/en-us/azure/defender-for-cloud/defender-for-containers-introduction)
