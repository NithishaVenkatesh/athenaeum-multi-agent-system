---
kind: module
id: do-c03-m03
vertical: devops-platform
course_id: do-c03
title: Security and compliance scanning
level: advanced
grounded_on: "AZ-400 skills outline (2026-04-24), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-400
synthetic: true
order: 3
prereqs: [do-c03-m01]
objectives:
  - Design a security-scanning strategy spanning dependencies, code, secrets, and licensing across the SDLC
  - Configure GitHub Advanced Security and Defender for Cloud DevOps capabilities
  - Automate container image and open-source dependency scanning in the pipeline
---

# Security and compliance scanning

Two weeks after Meridian Freight shipped the new rate-quote service, a researcher reported that a transitive dependency three levels deep in the build had a known remote-code-execution flaw with a public exploit. Nobody had chosen that library; it arrived as a dependency of a dependency. Separately, an intern's first pull request had pasted a real storage key into a test fixture, and it sat in the git history for a month. Neither problem needed a human to catch it — both are exactly what automated scanning catches, cheaply, on every commit. The discipline is *shift-left*: move detection as early in the SDLC as possible, where a finding is a code-review comment rather than a 2 a.m. incident.

## Learning objectives

By the end of this module you will be able to:

- Design a layered security-scanning strategy covering dependency, code, secret, and licensing analysis across the SDLC.
- Configure GitHub Advanced Security (code scanning, secret scanning, dependency review) for repositories.
- Use Microsoft Defender for Cloud DevOps connectors to gain a portfolio view of pipeline security.
- Automate container image and open-source dependency scanning, and triage Dependabot alerts.

## Concepts

### The four scanning surfaces

A complete strategy attacks four distinct surfaces, because each finds a different class of problem:

- **Dependency (SCA) scanning** inspects your open-source components against vulnerability databases. It is how you learn that a transitive package has a known CVE. GitHub's Dependabot raises *alerts* when a vulnerable dependency enters your graph and can open *update* pull requests automatically.
- **Code (SAST) scanning** analyzes your own source for vulnerable patterns — injection, unsafe deserialization, hardcoded crypto. On GitHub this is *code scanning*, typically powered by CodeQL, which queries code as if it were a database.
- **Secret scanning** looks for credentials — API keys, tokens, connection strings — committed to the repository, including in history. Push protection can *block* a commit that contains a recognized secret pattern before it ever lands.
- **Licensing scanning** flags open-source components whose license is incompatible with your distribution model, a compliance risk rather than a security one.

No single tool covers all four well; the strategy is to layer them so each surface is owned.

### Shift-left and where each gate lives

Scanning is only valuable if it runs where it changes a decision. Map each surface to a lifecycle point: secret push protection runs *at push*, before the secret is even in the remote; dependency review and SAST run *on the pull request*, so a reviewer sees findings inline and the branch policy can require they be resolved; container and full SCA scans run *in the build*, gating the artifact; and Defender for Cloud monitors *continuously* across the estate, catching drift in things that were clean yesterday. The earlier the gate, the cheaper the fix and the smaller the blast radius.

This connects directly to the quality and release gates you built in do-c02: a security finding becomes one more gate condition. A pull request with an unresolved critical CodeQL alert does not merge; a build that produces a container image with a high-severity OS package vulnerability does not promote.

### Defender for Cloud's DevOps view

Individual repository settings secure one repo at a time. Microsoft Defender for Cloud adds a *posture* layer: its DevOps security capability connects to your GitHub and Azure DevOps organizations and aggregates findings — exposed secrets, code scanning results, misconfigurations — into recommendations and a security score across your whole portfolio. This is the difference between "this repo is clean" and "every repo in the org is clean, and here are the three that are not." For a platform team owning many repositories, that aggregate view is where you actually manage risk.

## Walkthrough: hardening the rate-quote service pipeline

Meridian's platform team is adding scanning to the rate-quote service. They enable GitHub Advanced Security features on the repo, then add a build-time scan that fails on serious findings. First, the repository-level controls are turned on in repo settings (Security → Code security), enabling Dependabot alerts, code scanning, and secret scanning with push protection. Then they wire CodeQL into the pipeline:

```yaml
# .github/workflows/codeql.yml — SAST on every PR to main
name: CodeQL
on:
  pull_request:
    branches: [main]

permissions:
  security-events: write   # upload findings to the Security tab
  contents: read

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: github/codeql-action/init@v3
        with:
          languages: csharp
      - uses: github/codeql-action/autobuild@v3
      - uses: github/codeql-action/analyze@v3
```

For containers, they scan the image as part of the build and fail the job on high or critical findings so a vulnerable image never reaches the registry. Here using Trivy, a widely used open-source scanner, in a build step:

```yaml
  scan-image:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build image
        run: docker build -t ratequote:${{ github.sha }} .
      - name: Scan image, fail on HIGH/CRITICAL
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: ratequote:${{ github.sha }}
          severity: 'HIGH,CRITICAL'
          exit-code: '1'   # non-zero fails the job and blocks promotion
```

Finally, a branch protection rule on `main` requires both the CodeQL check and the image scan to pass, so the gates have teeth. With secret push protection on, the intern's pasted storage key is now rejected at `git push` with an explanation, and Dependabot opens a pull request the moment the vulnerable transitive package appears. The exact action versions and severity thresholds will shift over time — confirm current options in the docs — but the pattern of "scan early, gate the merge, gate the artifact" is stable.

## Common pitfalls

- **Scanning without gating.** Producing findings that nobody is required to act on trains the team to ignore them. Tie critical findings to branch policies and release gates so they block, as you learned to do with quality gates in do-c02.
- **Only scanning direct dependencies.** Most real vulnerabilities arrive transitively. Ensure SCA evaluates the full resolved dependency graph, not just your top-level manifest.
- **Detecting secrets after the push.** A secret found in history is already compromised and must be rotated, not just deleted. Enable *push protection* so the secret is blocked before it reaches the remote.
- **Alert fatigue with no triage path.** A wall of unprioritized findings gets muted wholesale. Triage by severity and exploitability, suppress false positives with documented justification, and let Dependabot auto-PR the low-risk upgrades.
- **Forgetting the container base image.** Your code can be clean while the base OS layer carries critical CVEs. Scan the built image, not only the application source, and rebuild on base-image updates.

## Knowledge check

1. Secret scanning finds an AWS-style key committed three weeks ago. Why is deleting it from the latest commit insufficient, and what should you do?
2. Your dependency scan only reads the top-level `packages.config`/`csproj` and reports no issues, yet a transitive package has a known CVE. What is wrong with the strategy?
3. A teammate argues that since CodeQL runs nightly, there is no need to run it on pull requests. Why is the PR gate still valuable?

<details>
<summary>Answers</summary>

1. The key was exposed in git history the moment it was pushed and must be treated as compromised — rotate (revoke and reissue) it, then remove it from history; deletion alone leaves a still-valid credential in the commit log. — Exposure, not current presence, is the trigger for rotation.
2. SCA must evaluate the full resolved dependency graph, including transitive dependencies, because most vulnerabilities arrive indirectly; scanning only direct manifests misses them. — You inherit the security of everything you pull in, not just what you name.
3. A nightly run finds the issue after it has merged, when fixing it is more expensive and may already be in a build; a PR gate surfaces it inline before merge, where it is a review comment. — Shift-left makes the finding cheaper by moving detection earlier.

</details>

## Summary

A security-scanning strategy layers four surfaces — dependency, code, secret, and licensing — and places each gate at the earliest lifecycle point where it changes a decision: push protection at push, SAST and dependency review on the pull request, container and full SCA scans in the build, and Defender for Cloud monitoring continuously across the portfolio. Findings only matter when they gate merges and artifacts, so tie them to the branch policies and release gates from do-c02. With infrastructure declared, secrets eliminated, and artifacts scanned, the final module makes the running platform observable so you can see, trace, and explain its behavior in production.

## Further learning

- [About GitHub Advanced Security](https://learn.microsoft.com/en-us/azure/devops/repos/security/github-advanced-security-overview)
- [Overview of Microsoft Defender for Cloud DevOps security](https://learn.microsoft.com/en-us/azure/defender-for-cloud/defender-for-devops-introduction)
- [About Dependabot alerts](https://learn.microsoft.com/en-us/azure/devops/repos/security/github-advanced-security-dependency-scanning)
- [About code scanning with CodeQL](https://learn.microsoft.com/en-us/azure/devops/repos/security/github-advanced-security-code-scanning)
