---
kind: module
id: do-c01-m01
vertical: devops-platform
course_id: do-c01
title: Choosing a branching strategy
level: foundational
grounded_on: "AZ-400 skills outline (2026-04-24), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-400
synthetic: true
order: 1
prereqs: []
objectives:
  - Compare trunk-based, feature-branch, and release-branch strategies
  - Select a branching model for a given team and release cadence
  - Map a branching model to environments
---

# Choosing a branching strategy

Meridian Tea Co., a fictional online retailer, has eight engineers and one painful ritual: every second Thursday is "merge day", when long-lived feature branches that have drifted for two or three weeks all try to land at once. Conflicts cascade, the build breaks, and someone stays late untangling a rebase. Nobody chose this; it accreted. The team blames Git, but Git is fine — the *branching strategy* is the problem, and they never actually picked one. Before you can fix a team's flow, you have to be able to name the models on the table and reason about why one fits a team and another fights it.

## Learning objectives

By the end of this module you will be able to:

- Compare trunk-based, feature-branch, and release-branch strategies on the axes that actually matter: branch lifetime, integration frequency, and merge risk.
- Select a branching model for a given team given its size, test maturity, and release cadence.
- Map a chosen branching model onto environments so that what is on a branch corresponds to what runs somewhere.

## Concepts

### The real variable is branch lifetime, not branch count

Every branching strategy is ultimately an answer to one question: *how long does code live in isolation before it integrates with everyone else's work?* The longer a branch lives apart, the more the rest of the codebase moves underneath it, and the more painful and risky the eventual merge. This is not a Git quirk; it is a fact about divergence. Two branches that share no commits for three weeks have three weeks of independent change to reconcile, and reconciliation cost grows faster than linearly because conflicts interact.

So when you compare strategies, the headline distinction is how aggressively each one drives integration. **Trunk-based development** pushes integration to the limit: everyone commits to a single shared branch (often called `main`) at least daily, in small increments, behind feature flags if a feature is not ready to be seen. Branches, if they exist at all, live hours, not weeks. **Feature-branch development** isolates each unit of work on its own branch that merges back when the feature is done — lifetimes of days to weeks. **Release-branch development** adds long-lived branches that represent a shippable line (for example `release/2.4`), so fixes can be made to a version in production independently of ongoing development.

These are not mutually exclusive religions. A pragmatic team often runs trunk-based development for daily work *and* cuts a short-lived release branch when it stabilizes a version. The mistake Meridian made was running feature branches with no discipline about lifetime — feature branching is fine; three-week feature branches are not.

### Matching the model to the team's reality

A branching model only works if the team's *test maturity* can support it. Trunk-based development depends on a fast, trustworthy automated test suite and continuous integration, because the safety net for "everyone commits to main constantly" is that a broken commit is caught in minutes and reverted. A team with flaky tests and a thirty-minute build cannot safely commit to trunk all day — they will block each other constantly. For that team, feature branches with a solid pull-request gate are the more honest fit *while they invest in test speed*.

Release cadence matters too. If you deploy continuously — many times a day — long release branches are friction you do not need; you want the shortest possible path from commit to production. If you ship a versioned product to customers who stay on old versions (think on-prem software), release branches are not optional, because you genuinely must patch 2.3 while 2.5 is in development. Ask three questions: How good is the test suite? How often do you release? Do you support multiple live versions at once? The answers point at a model.

### Mapping branches to environments

A branching strategy is incomplete until you decide what each branch *means* in terms of running software. A clean mapping makes the system legible: anyone can look at a branch name and know where that code is (or is heading). A common, sane mapping for a continuously-deployed service is: `main` is always deployable and is what flows to staging on every merge; a production deployment is a tagged commit on `main` that has passed staging. There is deliberately no permanent `develop` or per-environment branch, because extra long-lived branches reintroduce the divergence problem you were trying to avoid. Resist the urge to create a branch per environment (`dev`, `qa`, `prod`) — that pattern guarantees that "promoting" code means a merge, and merges between long-lived branches are exactly the pain you are trying to design out.

## Walkthrough: Meridian moves to trunk-based with flags

Meridian's team has decided to try trunk-based development, but they are nervous about a half-finished checkout redesign that cannot ship yet. The answer is a feature flag: the unfinished code can live on `main`, integrated continuously, but stays dark in production until it is ready. Here is the local workflow an engineer follows for a small, daily increment.

```bash
# Start from the latest main — short-lived branch, will live a few hours at most
git switch main
git pull --rebase origin main
git switch -c add-checkout-summary

# Make a small change, guarded by a feature flag so it can merge before it's "done"
cat >> src/checkout/summary.ts <<'EOF'
export function renderCheckoutSummary(cart: Cart): Summary {
  if (!isEnabled("checkout-redesign")) return legacySummary(cart);
  return newSummary(cart);
}
EOF

git add src/checkout/summary.ts
git commit -m "checkout: add summary renderer behind checkout-redesign flag"

# Integrate immediately. Rebase keeps history linear and surfaces conflicts now, while small.
git pull --rebase origin main
git push -u origin add-checkout-summary
```

The engineer opens a pull request, CI runs the fast test suite, a reviewer approves, and the branch merges into `main` the same afternoon — total branch lifetime measured in hours. The redesign code is on `main` and integrated, but `isEnabled("checkout-redesign")` returns `false` in production, so customers still see the legacy summary. When the redesign is complete and tested, flipping the flag — not merging a giant branch — is what ships it. Notice what changed: there is no merge day, because nothing drifts long enough to require one.

## Common pitfalls

- **Treating "feature branches" as license for long-lived branches.** The model is fine; the lifetime is the killer. Set a team norm — a branch that has not merged in two or three days is a smell to investigate, not a badge of thoroughness.
- **Adopting trunk-based development without the test suite to support it.** Committing to `main` all day with a slow, flaky build just moves the pain from merge day to every day. Invest in CI speed first, or stay on feature branches until you have.
- **Creating a branch per environment.** A `dev`/`qa`/`prod` branch hierarchy makes promotion a merge and reintroduces divergence between environments. Promote *artifacts and tags*, not branches.
- **Using a long-lived `develop` branch out of habit.** For a continuously-deployed service it usually adds a second integration point with no payoff. Only keep it if you can articulate the concrete problem it solves for *your* cadence.
- **Picking a model by fashion instead of by constraints.** "Trunk-based is best practice" is not an argument; a team supporting four live customer versions genuinely needs release branches. Reason from cadence, test maturity, and version support.

## Knowledge check

1. A team has a slow, occasionally flaky test suite and deploys once every two weeks. Should they adopt strict trunk-based development today? Why or why not?
2. Why does merge difficulty grow faster than linearly with branch lifetime, rather than proportionally?
3. A SaaS team wants `main` to always be deployable but also needs to ship an urgent fix to a version already in production. What branching arrangement satisfies both without long-lived environment branches?

<details>
<summary>Answers</summary>

1. No, not today — trunk-based development's safety net is a fast, trustworthy CI gate, which they lack; committing to `main` constantly with a flaky build would block the team. They should run disciplined short-lived feature branches *while* investing in test speed, then revisit. — Trunk-based requires a working safety net; without it the model amplifies pain.
2. Because conflicts interact — independent changes accumulate on both sides and overlapping edits compound, so reconciliation cost rises super-linearly as more divergent commits pile up. — Divergence, not branch count, drives merge cost.
3. Keep `main` always deployable for daily work and cut a short-lived release branch (e.g. `release/3.1`) only when patching the in-production version, then bring the fix back to `main`. — This isolates version maintenance without creating permanent per-environment branches.

</details>

## Summary

A branching strategy is fundamentally a decision about how long code is allowed to drift before it integrates, and the right choice falls out of three constraints: test maturity, release cadence, and how many live versions you support. Trunk-based development minimizes drift but demands a fast CI safety net; feature branches are fine when kept short; release branches earn their keep when you maintain shipped versions. Map branches to environments deliberately and avoid per-environment branches that turn promotion into a merge. The next module, **Pull requests, policies, and protection**, turns the merge points you have just designed into enforced quality gates.

## Further learning

- [Adopt a Git branching strategy](https://learn.microsoft.com/en-us/azure/devops/repos/git/git-branching-guidance)
- [What is trunk-based development?](https://learn.microsoft.com/en-us/devops/develop/how-microsoft-develops-devops)
- [Use feature flags in an ASP.NET Core app](https://learn.microsoft.com/en-us/azure/azure-app-configuration/use-feature-flags-dotnet-core)
