---
kind: module
id: as-c03-m02
vertical: architecture-security
course_id: as-c03
title: Designing security operations
level: advanced
grounded_on: "SC-100 skills outline (2026-04-27), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/sc-100
synthetic: true
order: 2
prereqs: [as-c03-m01]
objectives:
  - Design XDR and SIEM detection and response
  - Design SOAR with Sentinel and Defender XDR
  - Use MITRE ATT&CK to evaluate coverage
---

# Designing security operations

The Meridian Harbour strategy from the previous module made a promise: *assume breach*. That promise is empty until something is actually watching. Three weeks after rollout, a dispatcher's account signs in from an unfamiliar country at 3 a.m., creates an inbox rule that auto-deletes security alerts, and starts forwarding shipment manifests externally. Will anyone know before the data is gone? If the answer depends on a human noticing a line in a log, you have a strategy but no security operations. This module teaches you to design the detection-and-response capability that turns "assume breach" into "detect breach, then contain it automatically" — and to prove the design actually covers the attacks you care about.

## Learning objectives

By the end of this module you will be able to:

- Distinguish the roles of XDR and SIEM and design them to work together rather than overlap.
- Design automated response (SOAR) using Microsoft Sentinel playbooks and Defender XDR.
- Write a detection rule that turns raw telemetry into an actionable incident.
- Evaluate detection coverage against the MITRE ATT&CK matrix and identify the gaps that matter.

## Concepts

### XDR and SIEM: depth versus breadth

These two are constantly confused, so anchor the distinction. **XDR (extended detection and response)** — Microsoft Defender XDR — is the *depth* layer. It natively understands a specific set of estates (identities, endpoints, email, cloud apps, and cloud workloads), correlates signals *within* and *across* those domains, and produces high-fidelity incidents with built-in response actions like isolating a device or disabling a user. Because it owns the telemetry, it can act fast and with context.

**SIEM (security information and event management)** — Microsoft Sentinel — is the *breadth* layer. It ingests logs from anything that can emit them: firewalls, on-premises servers, SaaS apps, the acquired carriers' legacy systems, even custom appliances. Its job is organization-wide correlation, long retention for hunting and compliance, and a single pane across sources XDR does not natively cover.

The design pattern that works: let XDR own the estates it natively covers and stream its incidents *into* Sentinel, so Sentinel becomes the single investigation surface that correlates XDR's deep signals with everything else. You get depth where you have it and breadth everywhere else, without re-implementing XDR's detections by hand in the SIEM.

### Detections turn telemetry into incidents

Raw logs are not security value; a *detection* is. A detection is a rule that watches a stream and raises an alert when a pattern matches — an impossible-travel sign-in, a mass file download, a suspicious inbox rule. In Sentinel you express analytics rules in **KQL (Kusto Query Language)** against the tables in your Log Analytics workspace. Good detections are specific enough to avoid drowning analysts in false positives and general enough to catch variations of a technique. The art is choosing the signal that is hard for an attacker to avoid while doing the thing you care about.

### SOAR: automate the boring, urgent response

Detection without response is just faster anxiety. **SOAR (security orchestration, automation, and response)** closes the loop: when a detection fires, an automated workflow executes the first containment steps before a human is even awake. In Sentinel these workflows are **playbooks** built on Azure Logic Apps, triggered by an automation rule when an incident is created. A playbook for the 3 a.m. scenario might disable the user, revoke their sessions, open a ticket, and post to the SOC channel — in seconds. Reserve human judgment for decisions automation should not make; automate the deterministic, time-critical first response.

### MITRE ATT&CK: are we covering the right attacks?

You can have a hundred detections and still miss the attack that matters. **MITRE ATT&CK** is a public knowledge base of real adversary *tactics* (the attacker's goal — initial access, persistence, exfiltration) and *techniques* (how they achieve it). Used as a coverage map, you plot each of your detections against the techniques it catches. The gaps — techniques no detection covers — are where you are blind. This converts "do we have good monitoring?" from an opinion into a defensible heatmap you can show the board: here is what we detect, here is what we do not yet, here is the plan to close it.

## Walkthrough: catching exfiltration at Meridian Harbour

You will design a detection for the suspicious-inbox-rule-plus-mass-forward pattern, then auto-respond. Start with the analytics rule in KQL. Defender XDR's identity and cloud-app signals land in Sentinel tables; here you hunt for a risky inbox rule followed by anomalous outbound mail from the same user.

```kql
// Sentinel analytics rule: inbox manipulation + likely exfiltration (fictional thresholds)
let lookback = 1h;
let ruleCreations =
    CloudAppEvents
    | where Timestamp > ago(lookback)
    | where ActionType == "New-InboxRule" or ActionType == "Set-InboxRule"
    | where RawEventData has_any ("DeleteMessage", "MoveToFolder")
    | project RuleTime = Timestamp, AccountObjectId, RuleAction = ActionType;
let bulkForwards =
    EmailEvents
    | where Timestamp > ago(lookback)
    | where EmailDirection == "Outbound"
    | summarize SentCount = count() by SenderObjectId, bin(Timestamp, 10m)
    | where SentCount >= 25;   // tune to the org's normal baseline
ruleCreations
| join kind=inner bulkForwards on $left.AccountObjectId == $right.SenderObjectId
| project AccountObjectId, RuleTime, RuleAction, SentCount, Timestamp
```

The rule correlates two weak signals into one strong one: a stealthy inbox rule *and* a burst of outbound mail from the same identity in the same window is far more suspicious than either alone — and far less noisy. The `25` threshold and `10m` window are illustrative; you tune them against the organization's real baseline before going live. Note the join is the whole point: single-signal rules either miss or scream.

Next, wire the automated response. An automation rule binds the analytics rule to a playbook on incident creation.

```json
// Sentinel automation rule (conceptual shape — verify current schema in docs)
{
  "displayName": "Auto-contain inbox-rule exfiltration",
  "triggeringLogic": {
    "isEnabled": true,
    "triggersOn": "Incidents",
    "triggersWhen": "Created",
    "conditions": [
      { "property": "IncidentTitle", "operator": "Contains",
        "values": ["inbox manipulation"] }
    ]
  },
  "actions": [
    { "order": 1, "actionType": "RunPlaybook",
      "actionConfiguration": { "logicAppResourceId": "<contain-user-playbook-id>" } }
  ]
}
```

The playbook it runs (a Logic App) would revoke the user's sessions and disable the account via Microsoft Graph, then notify the SOC. The observable outcome: the same 3 a.m. scenario now ends with a contained account and a waiting ticket instead of leaked manifests. Finally, you tag this detection to the ATT&CK techniques it covers — collection via email rules and exfiltration over the mail channel — and add it to the coverage heatmap so the gap it closes is visible.

## Common pitfalls

- **Re-implementing XDR detections in the SIEM** — Duplicating Defender's native detections in Sentinel wastes effort and creates double alerts. Stream XDR incidents into Sentinel and let each layer do its job.
- **Single-signal detections** — A rule on inbox-rule creation alone is too noisy; on outbound volume alone, too blind. Correlate independent signals to get high-fidelity, low-noise incidents.
- **Automating decisions that need judgment** — Auto-disabling a service account that legitimately sends bulk mail can cause an outage. Automate deterministic containment; gate ambiguous actions behind human approval in the playbook.
- **Treating ATT&CK coverage as a checkbox** — A green technique with one brittle, untuned rule is not real coverage. Validate detections fire on simulated technique behavior, not just that a rule exists.
- **Ignoring retention and baseline** — Detections that compare against "normal" need enough history to know what normal is, and hunting needs retention. Size the workspace and retention to the detections and investigations you actually run.

## Knowledge check

1. A teammate proposes ingesting endpoint telemetry into Sentinel and writing Sentinel rules to detect malware, instead of using Defender XDR. What is the architectural objection?
2. Your impossible-travel detection fires 200 times a day and analysts have started ignoring it. Beyond raising the threshold, what design change reduces noise without losing real detections?
3. Leadership asks, "Are we protected against data exfiltration?" How does MITRE ATT&CK let you answer with evidence rather than an opinion?

<details>
<summary>Answers</summary>

1. Defender XDR natively understands endpoint telemetry and ships high-fidelity, context-rich detections with built-in response; re-deriving them in the SIEM duplicates work, loses context, and produces redundant alerts. Stream XDR incidents into Sentinel instead. — Use XDR for depth on estates it owns; use the SIEM for breadth.
2. Correlate the impossible-travel signal with a second independent signal (e.g., access to a sensitive resource or an anomalous action) so only the combination alerts — raising fidelity rather than just suppressing volume. — Multi-signal correlation cuts false positives without dropping true ones.
3. Map your detections to the ATT&CK exfiltration tactic's techniques and show which techniques are covered, which are not, and the remediation plan — turning a yes/no question into a coverage heatmap. — ATT&CK converts coverage from assertion into a defensible map.

</details>

## Summary

Security operations make "assume breach" real: XDR provides deep, native detection and response on the estates it owns, while Sentinel as your SIEM gives organization-wide breadth and a single investigation surface — you connect them rather than duplicate them. Detections written in KQL turn telemetry into high-fidelity incidents (correlate signals to cut noise), SOAR playbooks automate the urgent first response, and a MITRE ATT&CK coverage map turns "are we watching the right things?" into evidence. The next module shifts from catching attacks in motion to *reducing the attack surface itself* through posture management across hybrid and multicloud infrastructure.

## Further learning

- [Microsoft Sentinel documentation](https://learn.microsoft.com/en-us/azure/sentinel/overview)
- [Microsoft Defender XDR overview](https://learn.microsoft.com/en-us/defender-xdr/microsoft-365-defender)
- [Automate threat response with playbooks in Microsoft Sentinel](https://learn.microsoft.com/en-us/azure/sentinel/automate-responses-with-playbooks)
- [Understand security coverage by the MITRE ATT&CK framework in Microsoft Sentinel](https://learn.microsoft.com/en-us/azure/sentinel/mitre-coverage)
