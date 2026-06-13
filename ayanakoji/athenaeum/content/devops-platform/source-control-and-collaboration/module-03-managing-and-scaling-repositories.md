---
kind: module
id: do-c01-m03
vertical: devops-platform
course_id: do-c01
title: Managing and scaling repositories
level: foundational
grounded_on: "AZ-400 skills outline (2026-04-24), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-400
synthetic: true
order: 3
prereqs: [do-c01-m02]
objectives:
  - Manage large files with Git LFS
  - Configure repository permissions and tags
  - Apply a strategy for scaling a large Git repository
---

# Managing and scaling repositories

A new hire at Meridian Tea Co. tries to clone the `storefront` repo on their first morning and watches the progress bar crawl for eleven minutes before timing out. The repository is 3.8 GB. The code is maybe 90 MB of that; the rest is two years of accumulated PSD mockups, product photography, and a few sample videos someone committed directly — and because Git stores every version of every file forever, every revision of those binaries is baked into the history every clone must download. Once a large file is in history, deleting it from the working tree does nothing; the bytes are still in the past. This module is about keeping a repository fast and governable as it grows: where big files belong, who can do what, and how to organize history.

## Learning objectives

By the end of this module you will be able to:

- Manage large binary files with Git LFS so the repository stays fast to clone.
- Configure repository permissions so access matches responsibility, and use tags to mark meaningful points in history.
- Apply a strategy for scaling and optimizing a large Git repository, including shallow and partial clones.

## Concepts

### Why large binaries poison a Git repository, and how LFS fixes it

Git is content-addressed and keeps full history, which is exactly what you want for source code: every text revision is recoverable and diffs are small. Binaries break this model. A 40 MB image that changes ten times adds roughly 400 MB to history, because binaries don't delta-compress meaningfully — each version is stored whole. Worse, that weight is permanent and global: it is in the packfile every collaborator clones, forever, even after you "delete" the file.

**Git LFS (Large File Storage)** solves this by *not* putting the binary in Git history at all. When a path is tracked by LFS, Git stores a tiny text pointer (a hash and size) in the repository while the actual bytes go to a separate LFS store. A clone downloads the small pointers plus only the LFS objects the checked-out commit needs, not every version ever. You declare which paths LFS owns in a `.gitattributes` file, which is committed and so applies to everyone automatically. The critical caveat: LFS only helps files committed *after* you start tracking them. Binaries already in history stay there until you rewrite history to remove them — a heavier, coordinated operation you should treat as "verify the current tooling in the docs and plan a team cutover," not a casual command.

### Permissions: least privilege at the repository

A repository's permission model should follow the same principle as any access control — give each person the least they need. Both Azure Repos and GitHub express access through roles applied to users and groups: read (clone and view), write/contribute (push to non-protected branches, open PRs), and administrative permissions (manage settings, branch protection, and access itself). Prefer assigning permissions to *groups or teams*, not individuals, so joining a team grants the right access and leaving revokes it — per-person access is how stale permissions accumulate. Layer this on the branch protection from the previous module: a contributor can push to feature branches but cannot reach `main` except through a reviewed pull request. Permissions decide *which branches you can touch*; branch policies decide *how* `main` is changed.

### Tags and scaling techniques for large repos

A **tag** is a permanent, human-meaningful label for a specific commit — most often a release (`v2.4.0`). Unlike a branch, a tag does not move; it marks a point in history so you can later check out, build, or compare exactly what shipped. Use *annotated* tags for releases (they carry a message, author, and date and are objects in their own right) rather than lightweight tags, and keep a consistent naming scheme so the tag list is a readable timeline. Tags are how the traceability work in the next module anchors "what was deployed."

For scale itself, beyond LFS, the main levers reduce how much history a clone must transfer. A **shallow clone** (`--depth`) fetches only recent commits, which is ideal for CI agents that build once and discard the workspace. A **partial clone** (`--filter=blob:none`) fetches commit and tree objects but defers file contents until they are actually needed, which keeps large monorepos workable. **Sparse checkout** limits the working tree to the directories you care about. These are situational tools — a developer who needs full history shouldn't shallow-clone — but for build agents and very large repos they turn an eleven-minute clone into seconds.

## Walkthrough: Meridian moves design assets to LFS

Meridian decides that all images and video under `assets/` will be managed by LFS going forward, and they want CI agents to clone fast. First, an engineer installs and initializes LFS, declares the tracked paths, and commits the resulting `.gitattributes` so the rule applies to the whole team.

```bash
# One-time per machine; sets up the LFS Git filters
git lfs install

# Track binary asset types — this writes/updates .gitattributes
git lfs track "assets/**/*.png"
git lfs track "assets/**/*.mp4"

# Commit the rule itself so every collaborator gets the same behavior
git add .gitattributes
git commit -m "repo: manage png/mp4 assets under assets/ with Git LFS"

# Add a new asset: Git stores a small pointer, the bytes go to the LFS store
git add assets/hero/launch-banner.png
git commit -m "assets: add launch banner (stored via LFS)"
git push origin main
```

To confirm it worked, the engineer lists what LFS is managing and inspects the committed pointer rather than the raw binary:

```bash
git lfs ls-files                 # shows launch-banner.png tracked by LFS
git show HEAD:assets/hero/launch-banner.png   # prints a small pointer, not megabytes
```

The pointer output shows a `version`, an `oid` (the content hash), and a `size` — proof the repository now holds a reference, not the file. Separately, the platform team configures CI to clone shallowly so build agents stop pulling years of history:

```bash
git clone --depth 1 --branch main https://meridian.example/storefront.git
```

The combination — LFS for new binaries plus shallow clones on CI — fixes the *new* growth and the build-agent pain immediately. The 3.8 GB of binaries already in history still need a separate, planned history-rewrite cutover; that is a deliberate team operation, and the team should follow the current documented procedure and coordinate a re-clone for everyone, rather than rewriting shared history on a whim.

## Common pitfalls

- **Expecting LFS to shrink existing bloat.** Tracking a path with LFS only affects future commits; binaries already in history remain until you rewrite history. Plan that rewrite as a coordinated event and verify the recommended tooling in the docs.
- **Committing the binary before adding it to `.gitattributes`.** If you add the file in the same step before the track rule is in place, it can land in Git instead of LFS. Track the path (and commit `.gitattributes`) first, then add the file.
- **Assigning permissions to individuals instead of groups.** Per-person grants drift into a mess of stale access. Assign roles to teams so membership controls access and offboarding actually revokes it.
- **Using lightweight tags for releases.** Lightweight tags carry no author, date, or message, so your release history loses provenance. Use annotated tags for anything you might audit later.
- **Shallow-cloning where you need history.** `--depth 1` is great for throwaway CI workspaces but breaks operations that need the full graph (like blame across the whole history or bisecting an old regression). Match the clone depth to the task.

## Knowledge check

1. A team adds `*.psd` to LFS tracking today, but clones are still slow. What is the most likely reason, and what does fixing it require?
2. Why should repository permissions generally be granted to teams rather than to individual users?
3. A CI build agent clones the repo fresh for every run and never needs old history. Which clone option fits, and what is the tradeoff if a developer copies that habit?

<details>
<summary>Answers</summary>

1. The large `.psd` files are already in the existing history, which LFS tracking does not retroactively move; fixing it requires a coordinated history rewrite to purge the old blobs and a re-clone by the team. — LFS only governs files committed after tracking begins.
2. Because team-based grants make access follow role membership, so onboarding and offboarding automatically add and revoke the right permissions instead of leaving stale per-person access behind. — It keeps access aligned with responsibility over time.
3. A shallow clone (`--depth 1`) is ideal for the throwaway CI workspace; the tradeoff is that it lacks full history, so a developer who needs blame across all history or to bisect an old bug would be unable to. — Shallow clones trade history for speed and suit disposable workspaces only.

</details>

## Summary

A repository stays fast and governable when you keep large binaries out of Git history with LFS, grant least-privilege permissions through teams rather than individuals, and use annotated tags to mark meaningful points like releases. As repositories scale, shallow and partial clones and sparse checkout reduce what must be transferred — powerful for CI and large monorepos but matched to the task. Remember that LFS and these techniques govern future and current transfers; existing history bloat is a separate, planned cutover. The final module, **Traceability and flow of work**, builds on these tags and a clean repository to connect work items, commits, and deployments end to end.

## Further learning

- [Manage and store large files in Git with Git LFS](https://learn.microsoft.com/en-us/azure/devops/repos/git/manage-large-files)
- [Set Git repository permissions](https://learn.microsoft.com/en-us/azure/devops/repos/git/set-git-repository-permissions)
- [Use tags to mark important commits](https://learn.microsoft.com/en-us/azure/devops/repos/git/git-tags)
