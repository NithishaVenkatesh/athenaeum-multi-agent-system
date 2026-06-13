---
kind: module
id: as-c03-m01
vertical: architecture-security
course_id: as-c03
title: Zero-Trust strategy, MCRA, and MCSB
level: advanced
grounded_on: "SC-100 skills outline (2026-04-27), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/sc-100
synthetic: true
order: 1
prereqs: [as-c01, as-c02]
objectives:
  - Design a security strategy supporting business resiliency
  - Align solutions with MCRA and the cloud security benchmark
  - Apply a Zero-Trust rapid modernization plan
---

# Zero-Trust strategy, MCRA, and MCSB

Meridian Harbour Freight, a fictional regional logistics firm, just acquired two smaller carriers and inherited their networks, identity systems, and a flat trust model where being "inside the VPN" meant being trusted. The board has asked for a security strategy, and they do not want a shopping list of products — they want to know what the company will protect first, what it will assume is already breached, and how anyone will know if the plan is working. If you walk in with "we'll buy a SIEM and turn on MFA," you will lose the room. You need a strategy that ties security decisions to business resiliency, anchors them to a recognized architecture, and sequences the work so the riskiest gaps close first. That is what this module teaches.

## Learning objectives

By the end of this module you will be able to:

- Translate business resiliency goals into prioritized Zero-Trust security outcomes.
- Use the Microsoft Cybersecurity Reference Architectures (MCRA) to position capabilities and find architectural gaps.
- Map controls to the Microsoft cloud security benchmark (MCSB) to make a design auditable.
- Sequence remediation with a rapid modernization plan (RaMP) so the highest-impact work happens first.

## Concepts

### Zero Trust is three principles, not a perimeter

Zero Trust replaces the old "trusted network" model with three operating principles you apply everywhere. **Verify explicitly**: authenticate and authorize every request using all available signals — identity, device health, location, the sensitivity of what's being accessed — rather than trusting a network location. **Use least-privilege access**: grant just enough access, just in time, and let it expire. **Assume breach**: design as though an attacker is already inside, so you segment blast radius, encrypt end to end, and instrument everything for detection.

The mental shift that matters: the perimeter moves from the network edge to *each access decision*. A request from a corporate laptop on the office network gets no free pass; it is evaluated on its merits like any request from the public internet. This is why identity becomes the primary control plane in a Zero-Trust design — it is the one place every request must pass through.

### Strategy starts from resiliency, not technology

A security strategy that begins with products is a strategy you cannot defend. Begin instead with the business: what does Meridian Harbour need to keep running, and what is the cost of it stopping? A logistics firm whose dispatch system is down cannot move freight, so dispatch availability and the integrity of shipment data are resiliency goals. From those goals you derive security outcomes — "an attacker who phishes one dispatcher cannot reach the shipment database" — and only then do you choose controls.

Resiliency also means planning for *when* a control fails, not just *if*. Assume-breach thinking applied to strategy means you ask: if our identity provider is compromised, what still protects the data? Defense in depth — independent layers that each must be defeated — is how you answer that without a single point of failure.

### MCRA and MCSB: the map and the ruler

Two Microsoft references do different jobs. The **MCRA** is a set of architecture diagrams showing how security capabilities — identity, security operations, infrastructure protection, data protection — relate across an estate. Use it as a *map*: lay your current and proposed capabilities over it to see what is missing and how pieces should connect. It answers "does this design hang together?"

The **MCSB** is a control framework: a catalog of concrete security controls grouped into domains (network security, identity management, data protection, logging and threat detection, posture and vulnerability management, and more), each mapped to industry standards. Use it as a *ruler*: for every control, you can state whether you meet it and where the gap is. MCRA tells you the shape of the architecture; MCSB lets you measure it. A strong design document references both — the MCRA for the narrative, the MCSB for the line-item evidence.

### RaMP: sequence the work by risk

You cannot do everything at once, and trying to is how programs stall. A **rapid modernization plan (RaMP)** is an opinionated sequencing of Zero-Trust initiatives so you tackle the highest-leverage, breach-stopping work first — typically securing identity and access, then protecting privileged accounts and the most sensitive data, before broader modernization. RaMP is what turns a strategy into a roadmap a board will fund, because each phase delivers a measurable risk reduction rather than a vague "improvement."

## Walkthrough: a strategy artifact for Meridian Harbour

You will produce two things the board can act on: a prioritization decision and a control-mapping artifact. First, the RaMP sequencing, expressed as a structured design artifact so it is unambiguous in review.

```yaml
# meridian-zero-trust-ramp.yaml — Zero-Trust modernization sequence (fictional)
strategy:
  resiliency_goals:
    - id: G1
      goal: "Dispatch system stays available and shipment data stays intact"
      breach_assumption: "One dispatcher account will eventually be phished"
  phases:
    - phase: 1
      name: "Secure identity and access"
      rationale: "Identity is the primary control plane; close the most-used attack path first"
      initiatives:
        - "Enforce phishing-resistant MFA for all users via Conditional Access"
        - "Block legacy authentication protocols"
        - "Require compliant or hybrid-joined devices for sensitive apps"
      mcsb_controls: [IM-1, IM-6, IM-7]   # identity management domain
      success_metric: "100% of interactive sign-ins covered by Conditional Access"
    - phase: 2
      name: "Protect privileged access and critical data"
      rationale: "Limit blast radius once an account is compromised"
      initiatives:
        - "Just-in-time elevation for admin roles (PIM)"
        - "Classify and encrypt the shipment database"
      mcsb_controls: [PA-1, DP-3, DP-4]   # privileged access, data protection
      success_metric: "Zero standing global-admin assignments"
    - phase: 3
      name: "Detection, posture, and segmentation"
      rationale: "Assume breach: instrument and contain"
      mcsb_controls: [LT-1, NS-1, PV-2]
      success_metric: "Defender for Cloud Secure Score baseline established and trending up"
```

This artifact does the architect's real job: every initiative cites a resiliency goal, a rationale, the MCSB control domains it satisfies, and a measurable success metric. Now make Phase 1's first initiative concrete and auditable by checking that a phishing-resistant MFA policy actually exists, rather than trusting that someone enabled it.

```bash
# Verify a Conditional Access policy exists that enforces MFA org-wide.
# (Exact CA Graph schema evolves — verify current property names in the docs.)
az rest --method GET \
  --uri "https://graph.microsoft.com/v1.0/identity/conditionalAccess/policies" \
  --query "value[?state=='enabled'].{name:displayName, state:state}" -o table
```

Run against a tenant, this lists the enabled Conditional Access policies so you can confirm the MFA-enforcing policy is live and not left in report-only mode. The lesson: a strategy is only real when each phase resolves into a control you can *check*.

## Common pitfalls

- **Leading with products instead of resiliency goals** — You buy tools that do not map to any business outcome and cannot defend the spend. Always derive controls from a stated goal and breach assumption.
- **Treating MCRA as a diagram to copy** — The MCRA is a reference to map *your* estate against, not a target topology to clone. Use it to find gaps in how your capabilities connect.
- **Skipping the MCSB mapping** — Without line-item control mapping, "we do Zero Trust" is an assertion no auditor accepts. Map initiatives to MCSB control IDs so the design is measurable.
- **Boiling the ocean instead of sequencing** — Trying every Zero-Trust initiative simultaneously stalls the program. RaMP exists precisely to force risk-ordered phasing with deliverable milestones.
- **Leaving Conditional Access in report-only** — A policy in report-only mode looks enabled in a slide but enforces nothing. Verify enforcement state, not existence.

## Knowledge check

1. The board asks why your first modernization phase is "secure identity and access" rather than "deploy network firewalls everywhere." How do you justify the ordering?
2. A peer says the MCRA and the MCSB are redundant — "they both describe security." How are their roles in a design different?
3. You inherit a Conditional Access policy named "Require MFA — All Users." What would you check before claiming the organization enforces MFA?

<details>
<summary>Answers</summary>

1. Identity is the primary control plane in Zero Trust — every request passes through it — so closing the most-used attack path (credential compromise) delivers the largest risk reduction first, which is exactly what RaMP optimizes for. — RaMP sequences by breach-stopping impact, and identity is the highest-leverage layer.
2. The MCRA is a *map* showing how capabilities relate so you can spot architectural gaps; the MCSB is a *ruler* — a catalog of concrete controls you measure your design against. One gives narrative coherence, the other gives auditable evidence. — They are complementary: shape versus measurement.
3. Check that the policy's state is `enabled` (not report-only), that its assignment scope truly includes all users with no broad exclusions, and that it requires a phishing-resistant method rather than any second factor. — A policy can exist while enforcing nothing; state, scope, and strength all matter.

</details>

## Summary

A Zero-Trust strategy starts from business resiliency goals and the assumption of breach, then derives controls — never the reverse. You use the MCRA to map your capabilities and find architectural gaps, the MCSB to turn the design into auditable line-item controls, and a RaMP to sequence the work so the highest-impact, identity-first initiatives land first with measurable milestones. With the strategy and its control mapping in hand, the next module makes "assume breach" operational: designing the detection and response capability that tells you when the assumption comes true.

## Further learning

- [Zero Trust security model overview](https://learn.microsoft.com/en-us/security/zero-trust/zero-trust-overview)
- [Microsoft Cybersecurity Reference Architectures (MCRA)](https://learn.microsoft.com/en-us/security/adoption/mcra)
- [Microsoft cloud security benchmark overview](https://learn.microsoft.com/en-us/security/benchmark/azure/overview)
- [Zero Trust rapid modernization plan (RaMP)](https://learn.microsoft.com/en-us/security/zero-trust/zero-trust-ramp-overview)
