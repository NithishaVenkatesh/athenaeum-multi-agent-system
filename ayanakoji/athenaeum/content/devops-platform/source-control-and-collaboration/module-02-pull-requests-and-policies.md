---
kind: module
id: do-c01-m02
vertical: devops-platform
course_id: do-c01
title: Pull requests, policies, and protection
level: foundational
grounded_on: "AZ-400 skills outline (2026-04-24), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-400
synthetic: true
order: 2
prereqs: [do-c01-m01]
objectives:
  - Design a pull-request workflow with required reviews
  - Apply branch policies and protection rules
  - Implement merge restrictions that match risk
---

# Pull requests, policies, and protection

At Meridian Tea Co., the team has settled on short-lived branches and a trunk-based flow from the previous module. But there is a quiet rot in their review culture: pull requests get a thumbs-up within ninety seconds, often from whoever is closest to the keyboard, frequently with no comments and no evidence anyone read the diff. Then a config typo reaches `main`, the staging deploy fails, and the post-mortem reveals the "review" was a reflex. The fix is not "tell people to review harder." Humans drift; *policy* does not. This module is about turning the merge point you designed into an enforced gate — one that makes the safe path the only path, without strangling delivery.

## Learning objectives

By the end of this module you will be able to:

- Design a pull-request workflow that requires real review and passing checks before code can reach a protected branch.
- Apply branch policies and protection rules in Azure Repos and GitHub so the rules are enforced by the server, not by goodwill.
- Implement merge restrictions and required-reviewer rules that scale with the risk of the code being changed.

## Concepts

### Protection is server-side enforcement, not etiquette

A pull request is a *request* — a proposal to merge a branch. By itself it enforces nothing; a sufficiently motivated engineer can merge their own unreviewed branch in seconds. **Branch protection** (GitHub's term) and **branch policies** (Azure Repos' term) are the mechanism that turns the request into a gate the platform refuses to open until conditions are met. The crucial mental shift is that these rules live on the *server*, attached to the target branch (`main`), and apply to everyone including administrators if you configure them to. They are not a `.git/hooks` script that each developer can skip and not a convention in a wiki that people forget under deadline.

The building blocks are similar across both platforms: require a minimum number of approving reviews; require that specific status checks (your CI build, your tests, a security scan) pass; require that the branch is up to date with its target before merging; and disallow direct pushes to the protected branch so *all* changes flow through pull requests. Each rule closes a specific hole. "No direct pushes" closes the back door. "Require status checks" makes a green build a precondition, not a hope. "Require up to date" prevents the classic failure where two PRs each pass CI alone but break when combined.

### Reviews that mean something: who, how many, and reset-on-change

Requiring "one approval" is the floor, and a low one. Two refinements make required reviews actually protect quality. First, **required reviewers by path**: the people who own a sensitive area should be forced into the review for changes that touch it. In Azure Repos this is a *required reviewer* policy scoped to a path; in GitHub it is a `CODEOWNERS` file combined with "require review from Code Owners." A change to `infra/` should pull in the platform team automatically, every time, without the author having to remember.

Second, **dismiss stale approvals when new commits are pushed**. Without this, a reviewer approves a clean diff, the author then pushes three more commits "to address feedback," and the approval silently still counts — so the team merges code nobody approved. Resetting approval on new commits closes that gap. It is mildly annoying and completely worth it; the annoyance is the system doing its job.

### Match the restriction to the risk

Not all code carries equal risk, and a one-size gate is either too loose for the dangerous parts or too heavy for the trivial ones. The design principle is *proportionality*: heavier restrictions where a mistake is expensive, lighter where it is cheap. A change to billing logic or production infrastructure might require two approvals, a passing security scan, and a code owner; a typo fix in documentation might require one approval and the standard build. You implement this by scoping policies — different required reviewers and check requirements on different paths, plus branch-name patterns so the strictest rules guard `main` and release branches while a sandbox branch stays permissive. The goal is a gate strangers can pass safely and that does not make a one-line doc fix feel like shipping to a nuclear reactor.

## Walkthrough: Meridian enforces review on `main` with GitHub

Meridian's repo lives on GitHub. The team agrees on the rules and encodes them so no one can merge to `main` without review and a green build. First, they declare ownership of the risky areas with a `CODEOWNERS` file, so the platform and billing teams are pulled into the reviews that matter.

```text
# .github/CODEOWNERS — auto-requests these reviewers for matching paths
*                       @meridian/engineers
/infra/                 @meridian/platform
/src/billing/           @meridian/billing-leads
```

Then they apply a protection rule to `main`. Branch protection can be configured in the UI, but encoding it as an API call makes the intent explicit and reviewable. Using the GitHub CLI against the rules endpoint:

```bash
gh api --method PUT \
  repos/meridian/storefront/branches/main/protection \
  --input - <<'JSON'
{
  "required_status_checks": { "strict": true, "contexts": ["ci/build", "ci/test"] },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "require_code_owner_reviews": true,
    "dismiss_stale_reviews": true
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
```

Read it back against the rules: `strict: true` forces a branch to be up to date before merge, closing the "passed alone, broke together" gap; `contexts` makes the build and test checks mandatory; `require_code_owner_reviews` activates the `CODEOWNERS` ownership; `dismiss_stale_reviews` resets approval when new commits land; `enforce_admins` means even repo admins cannot bypass the gate; and `allow_force_pushes: false` plus `allow_deletions: false` protect the history of `main` itself. After this, an engineer who tries to push directly to `main` is rejected by the server, and a billing change cannot merge until a billing lead has actually approved the current commits with a green CI run. The exact field names and available options evolve, so verify the current schema in the GitHub branch-protection docs before scripting it for production.

## Common pitfalls

- **Relying on convention instead of enforcement.** "We agreed to always review" is not a control; the next deadline erases it. If a rule matters, put it in branch protection or a branch policy where the server enforces it.
- **Letting administrators bypass the gate.** If `enforce_admins` (or its Azure Repos equivalent) is off, the rules are advisory for the people most able to cause damage. Turn it on unless you have a deliberate break-glass process.
- **Forgetting to reset approvals on new commits.** Approving an early diff and then pushing more code merges unreviewed changes. Enable dismiss-stale-reviews so an approval applies only to the commits that were actually reviewed.
- **Skipping "require up to date before merge".** Two PRs can each pass CI in isolation and still break `main` when combined. Requiring the branch be current (GitHub's `strict`) re-runs checks against the merged state.
- **Uniform heavy policy everywhere.** If a doc typo needs two approvals and a security scan, people route around the process or stop contributing small fixes. Scale the restriction to the risk of the path being changed.

## Knowledge check

1. A reviewer approves a pull request, then the author pushes two more commits before merging. Which single policy ensures the new commits don't ship unreviewed, and why?
2. Why is requiring a branch to be "up to date with main before merge" different from simply requiring the build to pass on the branch?
3. The platform team must review every change to `infra/`, but the author keeps forgetting to add them. What mechanism enforces this automatically, and where is it configured?

<details>
<summary>Answers</summary>

1. Dismiss stale approvals on new commits — it resets the approval so the PR can't merge until someone approves the current commits. — An approval should certify the exact code being merged, not an earlier version of it.
2. Passing the build on the branch only proves the branch is good in isolation; "up to date" re-validates against the current target so two independently-green PRs can't combine into a broken `main`. — It guards against integration conflicts, not just per-branch correctness.
3. A `CODEOWNERS` file (GitHub) or a required-reviewer-by-path policy (Azure Repos), combined with "require review from code owners," auto-requests the owners for matching paths. — It moves the requirement from the author's memory into enforced policy.

</details>

## Summary

A pull request only protects quality when it is backed by server-side branch protection or branch policies that everyone — admins included — must satisfy. Require real reviews (ideally with code owners on risky paths and stale-approval dismissal), require passing and up-to-date status checks, and forbid direct pushes so all change flows through the gate. Then scale the strictness to the risk of the code, so the gate is proportionate rather than uniform. With merges now safe, the next module, **Managing and scaling repositories**, tackles keeping the repository itself fast and well-governed as it grows.

## Further learning

- [Branch policies and settings (Azure Repos)](https://learn.microsoft.com/en-us/azure/devops/repos/git/branch-policies)
- [Improve code quality with branch policies](https://learn.microsoft.com/en-us/azure/devops/repos/git/branch-policies-overview)
- [Set up required reviewers and approvals](https://learn.microsoft.com/en-us/azure/devops/repos/git/branch-policies)
