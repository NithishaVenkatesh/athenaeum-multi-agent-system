---
title: Compliance — disclaimer, prohibited content, security checklist
tags: [hackathon, compliance, requirement, synthetic-data]
status: stable
sources:
  - https://github.com/microsoft/Agents-League-AISF-Regulations (DISCLAIMER.md, SECURITY.md)
  - Reasoning Agents starter kit "Security, Synthetic Data, and Responsible AI"
updated: 2026-06-12
related: [official-rules, synthetic-data]
---

# Compliance (Disclaimer + starter-kit security rules)

Violations ⇒ content removal, **disqualification**, repo access revocation.

## Never include (anywhere in repo, history, video, or data)

- Azure API keys, connection strings, credentials, tokens, secrets
- Customer data or PII (real names, emails, real employee records)
- Company-confidential / internal engineering material not approved for open source
- Pre-release info under NDA, trade secrets, proprietary algorithms
- Third-party IP without license

Risk levels from the Disclaimer: Credentials = **Critical**; PII / proprietary code = **High**.

## Required practices

- `.env` in `.gitignore` from the first commit; never commit it
- Use environment variables / managed identity (`DefaultAzureCredential`); Key Vault for production secrets
- Scan for secrets before pushing (GitHub push protection is active on public repos)
- Review **git history**, not just working tree
- Demo + evaluation use **synthetic data only**, with clearly fabricated identifiers (`L-1001`, `EMP-001`, `TEAM-A`)
- README must state explicitly that all data is synthetic and for demonstration only

## Responsible AI expectations (judged under Reliability & Safety, 20%)

- Guardrails on inputs and outputs
- Safety validation where appropriate
- Test for bias / uneven outcomes
- Be transparent users are interacting with AI
- Human oversight for important decisions
- Manager-facing insights must not expose sensitive personal data (aggregate, don't name-and-shame)

## Other obligations

- Microsoft CLA may be required for contributions to MS repos (not for our own project repo)
- Private prep repos must go public within 90 days
- Security issues in MS repos: report via MSRC, **not** public issues
