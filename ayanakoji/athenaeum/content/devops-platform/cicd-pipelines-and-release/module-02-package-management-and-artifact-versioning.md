---
kind: module
id: do-c02-m02
vertical: devops-platform
course_id: do-c02
title: Package management and artifact versioning
level: intermediate
grounded_on: "AZ-400 skills outline (2026-04-24), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-400
synthetic: true
order: 2
prereqs: [do-c02-m01]
objectives:
  - Design package feeds with GitHub Packages or Azure Artifacts
  - Apply a dependency versioning strategy with SemVer or CalVer
  - Version pipeline artifacts reproducibly
---

# Package management and artifact versioning

Larkspur Robotics built a shared library, `larkspur-telemetry`, that every service uses to emit sensor metrics. For months it was copied as a folder into each repository. Then the warehouse team fixed a bug in their copy, the fleet team fixed a *different* bug in theirs, and now there are five subtly different "telemetry libraries" in production and no one can say which behavior is correct. The pipeline you built in **Building pipelines with YAML** can compile each service, but it cannot answer the question that matters: *which version of the shared code is this build actually using?* The fix is to stop copying source and start publishing versioned packages to a feed that everyone consumes from.

## Learning objectives

By the end of this module you will be able to:

- Design and configure a package feed using GitHub Packages or Azure Artifacts, including upstream sources.
- Choose and apply a dependency versioning strategy — SemVer or CalVer — and explain the trade-off.
- Version the artifacts your pipeline produces so that any deployed build is traceable to exact inputs.

## Concepts

### Feeds, and why upstream sources matter

A **feed** is a hosted catalog of packages — npm, NuGet, Maven, Python, and more — that your builds publish to and pull from. Instead of vendoring source, a service declares "I depend on `larkspur-telemetry` version 2.3.1" and the build restores that exact package from the feed. There is now one authoritative artifact per version, immutable once published.

The feature that makes a feed an organizational asset rather than a private cache is the **upstream source**. You configure your feed to proxy a public registry (the public npm or NuGet gallery, say). When a build asks for a package the feed has never seen, the feed fetches it from upstream, *saves a copy*, and serves it. From then on you are insulated from the public registry going down or a version being deleted — you have your own stored copy. It also gives you a single chokepoint where security and license policy can be enforced, instead of every developer reaching out to the open internet independently. The specifics of how retention and saved upstream copies are configured change over time, so confirm the current behavior in the docs before you rely on a particular retention guarantee.

### Views: separating "tested" from "published"

A mature feed exposes **views** — named slices of the feed at different quality levels, conventionally `@local`, `@prerelease`, and `@release`. A package is first promoted into a prerelease view for integration testing, and only promoted to the release view once it has earned trust. Consumers choose which view to point at: a downstream service under active development might track `@prerelease` to get early access, while a production build pins to `@release`. Views let a single immutable artifact flow through quality stages without ever being rebuilt or renamed — you promote the *same bytes*, which is exactly what makes the promotion meaningful.

### SemVer versus CalVer

A version string is a promise to consumers, and the scheme you pick determines what that promise says. **Semantic Versioning (SemVer)** uses `MAJOR.MINOR.PATCH`: bump PATCH for backward-compatible bug fixes, MINOR for backward-compatible new features, and MAJOR when you break compatibility. Its whole value is that a consumer can read `2.4.1 → 2.5.0` and know, without a changelog, that nothing they depend on was removed. This is the right default for libraries other code links against — like `larkspur-telemetry`.

**Calendar Versioning (CalVer)** encodes the release date, e.g. `2026.04.0`. It communicates recency rather than compatibility, which fits products that ship continuously and whose "breaking change" concept is fuzzy — an end-user application or a service image more than a linked library. The mistake is mixing intents: do not apply SemVer to something whose consumers do not actually reason about compatibility, and do not apply CalVer to a library where consumers desperately need to know whether an upgrade is safe.

## Walkthrough: publishing larkspur-telemetry to a feed

Larkspur will turn `larkspur-telemetry` into an npm package published to Azure Artifacts, versioned with SemVer, and have the warehouse service consume it. First, the package declares its version explicitly in `package.json`:

```json
{
  "name": "@larkspur/telemetry",
  "version": "2.4.1",
  "main": "dist/index.js"
}
```

The build pipeline restores from the feed, builds, runs tests, and publishes. The `.npmrc` points npm at the feed's registry; the pipeline authenticates with a task that injects feed credentials so no token is hard-coded:

```yaml
stages:
  - stage: PublishPackage
    jobs:
      - job: pack_and_push
        pool: { vmImage: 'ubuntu-latest' }
        steps:
          - task: UseNode@1
            inputs:
              version: '20.x'
          # Inject feed auth into .npmrc — no secrets in source
          - task: npmAuthenticate@0
            inputs:
              workingFile: '.npmrc'
          - script: npm ci && npm run build && npm test
            displayName: 'Build and test'
          - script: npm publish
            displayName: 'Publish @larkspur/telemetry to feed'
```

The consuming warehouse service adds an `.npmrc` pointing at the same feed and depends on the package by version range:

```jsonc
// warehouse-service/package.json (excerpt)
{
  "dependencies": {
    "@larkspur/telemetry": "^2.4.1"  // accepts 2.x, not 3.x
  }
}
```

The `^2.4.1` range is a direct consequence of SemVer: the caret accepts any `2.x` release because those are promised backward-compatible, but it refuses `3.0.0`, which by definition may break. The crucial reproducibility step is committing the lockfile (`package-lock.json`): the range says what is *allowed*, but the lockfile pins the *exact* resolved version, so two builds a month apart produce identical dependency trees. The precise pipeline task names and authentication mechanics differ between Azure Artifacts and GitHub Packages and evolve over time — verify the current task and `.npmrc` registry format in the docs for your feed.

## Common pitfalls

- **Vendoring shared code instead of packaging it.** Copying a library folder into each repo guarantees divergence. Publish one versioned package and consume it everywhere so there is a single source of truth.
- **Not committing the lockfile.** Without `package-lock.json` (or its NuGet/Maven equivalent), a version range resolves differently over time and "works on my machine" becomes "worked last Tuesday." Commit the lockfile and treat it as part of the build.
- **Reusing or overwriting a published version.** Republishing `2.4.1` with different bytes breaks the immutability consumers rely on. Every change gets a new version; published versions are never altered.
- **Applying the wrong versioning scheme.** SemVer on a continuously shipped app, or CalVer on a linked library, sends a signal consumers cannot act on. Match the scheme to whether consumers reason about compatibility or recency.
- **Skipping upstream sources and letting every build hit the public internet.** This leaves you exposed to upstream outages and removed packages, and removes the policy chokepoint. Proxy public registries through your feed.

## Knowledge check

1. A teammate proposes bumping a widely linked library from `2.4.1` to `3.0.0` to ship a bug fix. Under SemVer, what does that version change signal, and is it appropriate for a bug fix?
2. Your CI builds pass locally but a build last month used a different transitive dependency version than today's, causing a regression. What practice would have prevented this?
3. Why does promoting a package between feed views (e.g. prerelease → release) not require rebuilding it, and why is that property valuable?

<details>
<summary>Answers</summary>

1. `3.0.0` signals a breaking, backward-incompatible change. A pure bug fix should be a PATCH bump (`2.4.2`); using a MAJOR bump falsely warns consumers of incompatibility and may block their automatic upgrades. — SemVer's MAJOR digit is reserved for compatibility breaks.
2. Committing and restoring from a lockfile, which pins exact resolved versions of all dependencies, so builds are reproducible over time. — Version ranges allow drift; lockfiles freeze it.
3. Promotion moves the same immutable artifact between quality views without producing new bytes, so the thing tested is exactly the thing released. That byte-for-byte identity is what makes the promotion a trustworthy quality signal. — Rebuilding would risk shipping something different from what was tested.

</details>

## Summary

Packages and feeds replace copied source with one immutable, versioned, traceable artifact per change; upstream sources insulate you from the public internet and centralize policy; and views let a single artifact flow through quality stages without being rebuilt. Versioning is a promise — SemVer for compatibility, CalVer for recency — and lockfiles turn that promise into reproducible builds. With dependencies and artifacts under control, the next module, **Testing strategy and quality gates**, decides which of those artifacts have earned the right to advance.

## Further learning

- [What is Azure Artifacts?](https://learn.microsoft.com/en-us/azure/devops/artifacts/start-using-azure-artifacts)
- [Use upstream sources in a feed](https://learn.microsoft.com/en-us/azure/devops/artifacts/concepts/upstream-sources)
- [Feed views](https://learn.microsoft.com/en-us/azure/devops/artifacts/concepts/views)
- [Publish and consume npm packages with Azure Artifacts](https://learn.microsoft.com/en-us/azure/devops/artifacts/get-started-npm)
