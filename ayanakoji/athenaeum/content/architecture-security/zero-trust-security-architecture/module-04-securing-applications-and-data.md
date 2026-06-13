---
kind: module
id: as-c03-m04
vertical: architecture-security
course_id: as-c03
title: Securing applications and data
level: advanced
grounded_on: "SC-100 skills outline (2026-04-27), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/sc-100
synthetic: true
order: 4
prereqs: [as-c03-m02, as-c03-m03]
objectives:
  - Design a lifecycle strategy for application security
  - Secure APIs and applications with WAF and workload identities
  - Protect data with classification, encryption, and Defender
---

# Securing applications and data

Everything in this course so far has been working toward the things an attacker actually wants: Meridian Harbour's customer-facing shipment-tracking app and the database of manifests behind it. The app exposes a public API; the database holds personal and commercial data the acquired carriers never classified. A strong identity strategy, good detection, and clean posture still leave you exposed if the application accepts a malicious payload, the API trusts a forged caller, the service authenticates with a secret pasted into a config file, or the data sits unencrypted and unlabeled. This module teaches you to design defense in depth for the application and data tiers — the last and most valuable layers of the Zero-Trust architecture.

## Learning objectives

By the end of this module you will be able to:

- Design a full-lifecycle application security strategy from design through runtime.
- Secure public APIs and applications using Azure Web Application Firewall and gateway controls.
- Replace secrets with workload identities so services authenticate without stored credentials.
- Protect data with classification, encryption at rest and in transit, and Key Vault, evaluating where each applies.

## Concepts

### Application security is a lifecycle, not a gate

Treating security as a scan before release guarantees you find problems when they are most expensive to fix. A lifecycle strategy embeds security across every phase: **design** (threat modeling — asking how each component could be abused), **develop** (secure coding, dependency scanning, secret detection in the pipeline), **deploy** (infrastructure-as-code review, no secrets in config), and **operate** (runtime protection, monitoring, and the detection you built in module two). Each phase has cheaper fixes than the next, so the strategy front-loads effort. The architect's job is to specify *which* control lives at *which* phase, not to bolt a WAF on at the end and call it secure.

### WAF and API security: distrust the request

A public endpoint receives hostile traffic by default, so the request itself must be inspected. **Azure Web Application Firewall (WAF)** sits in front of the app — on Application Gateway for regional workloads or Azure Front Door for global — and inspects HTTP traffic against managed rule sets (such as the OWASP core rules) to block common attacks like SQL injection and cross-site scripting before they reach the app. WAF is your inspection layer for the *content* of requests.

APIs need a second discipline beyond WAF. An **API management** layer (such as Azure API Management) gives you a single front door where you enforce authentication, validate tokens, rate-limit abusive callers, and hide backend topology. WAF asks "is this request malicious?"; the API gateway asks "is this caller allowed, and are they within their quota?" Both, together, embody verify-explicitly at the application edge.

### Workload identities: stop storing secrets

The most common application credential leak is a connection string or API key checked into source or pasted into an app setting. The Zero-Trust answer is to remove the secret entirely. A **managed identity** gives an Azure service its own identity in Microsoft Entra ID; the service requests short-lived tokens at runtime and never holds a long-lived secret. Your app authenticates to Key Vault, a database, or storage *as itself*, and you grant that identity least-privilege access. Where a secret is genuinely unavoidable, it lives in **Azure Key Vault** — not in config — and the app reads it using its managed identity. In code, `DefaultAzureCredential` makes this seamless: it uses the managed identity in Azure and a developer's login locally, so the same code runs in both places with no secret.

### Data protection: classify, then encrypt, then watch

You cannot protect data uniformly because not all data is equal — so you start by knowing what you have. **Data discovery and classification** (Microsoft Purview) scans stores, identifies sensitive data such as personal or financial information, and applies sensitivity labels that downstream controls can act on. Then **encryption**: data at rest is encrypted by Azure platform-side by default, and you decide whether platform-managed keys suffice or whether a regulatory requirement calls for customer-managed keys held in Key Vault; data in transit is protected with TLS, which you enforce (reject anything older or unencrypted). Finally, you *watch* the data: Microsoft Defender for the relevant data services detects anomalous access — the mass-export pattern that should never be normal. Classification tells you what matters, encryption protects it at rest and in motion, and detection catches misuse.

## Walkthrough: hardening the shipment-tracking stack

You will eliminate the database secret from Meridian Harbour's tracking API and front it with a WAF. First, the application connects to Azure SQL using its managed identity — no connection-string password anywhere.

```python
# Tracking API: connect to Azure SQL using a managed identity, no stored secret.
import struct
from azure.identity import DefaultAzureCredential
import pyodbc

# DefaultAzureCredential uses the app's managed identity in Azure,
# and the developer's signed-in identity locally — same code, no secret.
credential = DefaultAzureCredential()
token = credential.get_token("https://database.windows.net/.default")

# Azure SQL expects the access token via the SQL_COPT_SS_ACCESS_TOKEN attribute (1256).
token_bytes = token.token.encode("utf-16-le")
token_struct = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)
SQL_COPT_SS_ACCESS_TOKEN = 1256

conn = pyodbc.connect(
    "Driver={ODBC Driver 18 for SQL Server};"
    "Server=tcp:meridian-tracking.database.windows.net,1433;"
    "Database=shipments;Encrypt=yes;TrustServerCertificate=no;",
    attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct},
)
```

There is no password in this code, in config, or in source control — the credential is a short-lived token tied to the app's identity, and `Encrypt=yes` enforces TLS in transit. Next, put a WAF in front of the public endpoint. This Bicep enables a WAF policy in Prevention mode using the OWASP managed rule set.

```bicep
// WAF policy for the tracking app's front door (Bicep).
// Rule-set versions change — verify the current managed rule set version in the docs.
resource wafPolicy 'Microsoft.Network/ApplicationGatewayWebApplicationFirewallPolicies@2023-09-01' = {
  name: 'meridian-tracking-waf'
  location: resourceGroup().location
  properties: {
    policySettings: {
      state: 'Enabled'
      mode: 'Prevention'          // block, don't just log
      requestBodyCheck: true
    }
    managedRules: {
      managedRuleSets: [
        {
          ruleSetType: 'OWASP'
          ruleSetVersion: '3.2'   // confirm latest supported version before deploy
        }
      ]
    }
  }
}
```

In Prevention mode the WAF blocks matching attacks outright rather than only logging them. The observable result: an injection attempt against the tracking API is rejected at the edge, the app authenticates to its database with no stored secret, and traffic is encrypted end to end — defense in depth across the application and data tiers.

## Common pitfalls

- **Security as a release gate** — Finding flaws only in a pre-ship scan makes them the most expensive to fix. Distribute controls across design, develop, deploy, and operate.
- **WAF left in Detection mode** — A WAF that only logs gives a false sense of safety while attacks still land. Move to Prevention mode once tuned, and verify it blocks.
- **Storing secrets "temporarily" in app settings** — Temporary becomes permanent and leaks. Use managed identities; reserve Key Vault for the unavoidable secret, accessed via that identity.
- **Encrypting everything but classifying nothing** — Uniform encryption without classification means you cannot apply stronger controls where they are needed or prove compliance. Discover and label data first, then protect by sensitivity.
- **Confusing WAF with API authorization** — WAF inspects request content; it does not decide whether a caller is authorized or within quota. Pair it with an API gateway that validates tokens and rate-limits.

## Knowledge check

1. Your team wants to "add security at the end" by deploying a WAF before go-live. Why is that insufficient as an application security *strategy*, and what does a lifecycle approach add?
2. A service reads a database password from an app setting that is itself stored in Key Vault. A reviewer says this still is not Zero Trust. What stronger design removes the weakness, and why is it better?
3. Two stores hold data: one with public route schedules, one with customer personal data. Why does designing identical encryption and monitoring for both reflect a flawed approach, and what should drive the difference?

<details>
<summary>Answers</summary>

1. A pre-go-live WAF catches only edge attacks and finds design and code flaws at the most expensive moment; a lifecycle strategy threat-models at design, scans dependencies and secrets during development, reviews IaC at deploy, and monitors at runtime — cheaper fixes, broader coverage. — Security distributed across phases beats a single gate.
2. Give the service a managed identity and have it read the secret (or connect directly) using short-lived tokens, so no long-lived password exists for the service to hold or leak; it is better because removing the standing secret eliminates the credential as an attack target. — Workload identity beats stored-secret retrieval.
3. Treating all data identically wastes strong controls on low-value data and under-protects sensitive data; data classification should drive the level of encryption (e.g., customer-managed keys), access restriction, and anomaly monitoring applied. — Classify first, then protect proportionally.

</details>

## Summary

The application and data tiers are where the attacker's goal lives, so they get defense in depth: a lifecycle strategy places controls from design through runtime, a WAF inspects request content while an API gateway authorizes callers, managed identities remove stored secrets so services authenticate as themselves, and data is classified, encrypted at rest and in transit, and watched for anomalous access. Together with the strategy, detection, and posture work from the earlier modules, you now have a complete Zero-Trust architecture — verify explicitly, least privilege, assume breach — applied coherently from the boardroom strategy down to the bytes in the database, which is exactly the end-to-end design this vertical set out to teach.

## Further learning

- [Azure Web Application Firewall documentation](https://learn.microsoft.com/en-us/azure/web-application-firewall/overview)
- [What are managed identities for Azure resources?](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/overview)
- [Azure Key Vault overview](https://learn.microsoft.com/en-us/azure/key-vault/general/overview)
- [Data classification in Microsoft Purview](https://learn.microsoft.com/en-us/purview/data-classification-overview)
