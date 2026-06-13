---
kind: module
id: do-c02-m01
vertical: devops-platform
course_id: do-c02
title: Building pipelines with YAML
level: intermediate
grounded_on: "AZ-400 skills outline (2026-04-24), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-400
synthetic: true
order: 1
prereqs: [do-c01]
objectives:
  - Develop multi-stage pipelines in YAML
  - Create reusable templates, variables, and variable groups
  - Implement trigger rules and job execution order
---

# Building pipelines with YAML

At Larkspur Robotics, the build process lives in someone's head. When a release goes out, an engineer named Priya opens the classic visual pipeline editor, clicks through a dozen tasks she half-remembers configuring last quarter, and hopes the staging credentials are still valid. When Priya is on leave, releases stop. Nobody can review a change to the build the way they review a change to the code, because the build is not code — it is a pile of clicks in a web UI. Your job is to turn that pile of clicks into a file: reviewable, versioned, and diffable, sitting in the repository next to the application it ships.

## Learning objectives

By the end of this module you will be able to:

- Develop a multi-stage YAML pipeline with discrete build, test, and deploy stages.
- Factor repeated logic into reusable templates and centralize configuration in variables and variable groups.
- Control when a pipeline runs and in what order its jobs execute, including parallel and dependent work.

## Concepts

### The pipeline hierarchy: stages, jobs, and steps

A YAML pipeline is a nested structure, and getting the levels right is most of the battle. At the top are **stages** — major phases of delivery such as "Build", "Test", and "DeployToStaging". A stage is a unit you can gate, approve, or rerun on its own. Inside a stage are **jobs**, and this is the important boundary: each job runs on its own agent (a fresh machine or container). Two jobs do *not* share a filesystem unless you explicitly publish and download artifacts between them. Inside a job are **steps** — the individual `script` or task invocations that actually do work, running in sequence on that one agent.

The mental model that prevents the most pain: *a job is a sandbox*. Anything you produce in one job and need in another must be handed across deliberately. New engineers routinely write a build job and a deploy job and are baffled that the deploy job cannot find the compiled output — because they imagined one long script when there were really two isolated machines.

### Dependencies and execution order

By default, stages run one after another in the order written, and jobs within a stage run in **parallel** (subject to how many parallel agents your organization has). You change this with `dependsOn`. A job or stage with `dependsOn` waits for its named predecessors to succeed before starting. This is how you express a graph: fan out three independent test jobs in parallel, then have a "Publish" job that `dependsOn` all three and runs only after every one passes.

You also control flow with `condition`. A stage might run only on the main branch, or a cleanup job might run `always()` even when earlier work failed. Parallelism is not just a speed trick — it is how you keep a pipeline honest. If your unit tests and your linting are truly independent, running them as parallel jobs surfaces *both* failures in one run instead of making you fix one, push, and discover the next.

### Templates, variables, and variable groups

Repetition in a pipeline is a liability, because every copy drifts. **Templates** are the cure. A template is a YAML file containing a reusable fragment — a set of steps, a whole job, or a whole stage — that you reference with parameters. When ten microservices all build the same way, you write the build steps once in a template and have each service's pipeline call it with its own name and path. Fix a bug in the template, and all ten inherit the fix.

**Variables** hold values your pipeline reads at runtime. Define them inline for things specific to one pipeline, but pull shared and sensitive values from a **variable group** — a named, central collection (often backed by a secret store) that many pipelines reference. The discipline here is the same as in application code: never hard-code an environment URL or a connection string into a step, because the moment you need a second environment you will copy the whole file and create two things that must be kept in sync by hand.

## Walkthrough: Larkspur's order-service pipeline

Priya wants to replace the click-driven build for Larkspur's `order-service` with a multi-stage pipeline. It should build the app, run tests in parallel with linting, and deploy to staging only on the `main` branch. Here is the pipeline, with a small template for the shared build steps.

First, the reusable build template, `templates/dotnet-build.yml`:

```yaml
# templates/dotnet-build.yml — reusable build steps
parameters:
  - name: projectPath
    type: string

steps:
  - task: UseDotNet@2
    inputs:
      packageType: sdk
      version: '8.x'
  - script: dotnet build ${{ parameters.projectPath }} --configuration Release
    displayName: 'Build ${{ parameters.projectPath }}'
```

Now the main pipeline, `azure-pipelines.yml`:

```yaml
trigger:
  branches:
    include: [main]
  paths:
    include: [src/order-service/*]

variables:
  - group: order-service-shared   # variable group with staging URL, etc.
  - name: projectPath
    value: 'src/order-service/OrderService.csproj'

stages:
  - stage: Build
    jobs:
      - job: build
        pool: { vmImage: 'ubuntu-latest' }
        steps:
          - template: templates/dotnet-build.yml
            parameters:
              projectPath: $(projectPath)

  - stage: Verify
    dependsOn: Build
    jobs:
      - job: tests          # runs in parallel with 'lint'
        pool: { vmImage: 'ubuntu-latest' }
        steps:
          - script: dotnet test $(projectPath) --logger trx
            displayName: 'Run unit tests'
      - job: lint           # no dependsOn, so parallel with 'tests'
        pool: { vmImage: 'ubuntu-latest' }
        steps:
          - script: dotnet format --verify-no-changes
            displayName: 'Check formatting'

  - stage: DeployStaging
    dependsOn: Verify
    condition: and(succeeded(), eq(variables['Build.SourceBranch'], 'refs/heads/main'))
    jobs:
      - deployment: deploy
        environment: staging
        pool: { vmImage: 'ubuntu-latest' }
        strategy:
          runOnce:
            deploy:
              steps:
                - script: echo "Deploying to $(stagingUrl)"
                  displayName: 'Deploy to staging'
```

Three things to observe. The `trigger.paths` filter means a change to an unrelated service does not run this pipeline at all. The `Verify` stage has two jobs with no `dependsOn` between them, so they run concurrently and report both results. And `DeployStaging` runs only when the prior stage succeeded *and* the branch is `main`, so a feature branch can be built and tested without ever touching staging. The exact agent pool images and the precise condition functions are the kind of detail that evolves — verify the current expression syntax and available `vmImage` values in the docs.

## Common pitfalls

- **Assuming jobs share a filesystem.** Each job runs on a fresh agent. If a later job needs build output, publish it as a pipeline artifact and download it explicitly; do not expect a path from an earlier job to exist.
- **Hard-coding environment values in steps.** A connection string or URL pasted into a `script` becomes unmanageable the moment you add a second environment. Put it in a variable group from day one.
- **Overusing `dependsOn` and serializing everything.** Adding `dependsOn` to jobs that are actually independent forfeits parallelism and slows every run. Only declare a dependency when one job genuinely consumes another's output.
- **Forgetting trigger path and branch filters.** Without `paths`/`branches` filters, every commit anywhere triggers every pipeline, burning agent minutes and creating noise that trains the team to ignore pipeline results.
- **Copy-pasting pipelines instead of templating.** Duplicated YAML drifts. The second copy gets a fix the first never receives, and you debug a "flaky" difference that is really two divergent files.

## Knowledge check

1. You have a build job and a separate deploy job. The deploy job fails with "file not found" looking for the compiled binary. What is the most likely cause and the fix?
2. Your unit-test job and your lint job both have `dependsOn: Build` but neither depends on the other. Do they run in sequence or in parallel, and why might you want it that way?
3. You want a deploy stage to run only for the `main` branch after tests pass. Which two mechanisms combine to express that?

<details>
<summary>Answers</summary>

1. The jobs run on separate agents with separate filesystems — Build's output never reached Deploy. Fix it by publishing the binary as a pipeline artifact in Build and downloading it in Deploy. — Jobs are isolated sandboxes; cross-job data must be passed explicitly.
2. In parallel, because neither lists the other in `dependsOn`. You want this so both failures surface in a single run instead of one masking the other. — Independent jobs default to concurrent execution within a stage.
3. A stage-level `dependsOn` on the test stage plus a `condition` checking both `succeeded()` and the source branch equals `refs/heads/main`. — `dependsOn` orders the work; `condition` decides whether it runs at all.

</details>

## Summary

A YAML pipeline turns your delivery process into reviewable, versioned code organized as stages of jobs of steps — where every job is an isolated sandbox, dependencies form an explicit graph, and templates plus variable groups keep repetition and secrets under control. With a pipeline that builds, verifies in parallel, and gates deployment on branch and success, Larkspur can ship without depending on one person's memory. The next module, **Package management and artifact versioning**, takes the artifacts this pipeline produces and gives them durable identities so consumers can depend on them reliably.

## Further learning

- [What is Azure Pipelines?](https://learn.microsoft.com/en-us/azure/devops/pipelines/get-started/what-is-azure-pipelines)
- [Add stages, dependencies, and conditions](https://learn.microsoft.com/en-us/azure/devops/pipelines/process/stages)
- [Template types and usage](https://learn.microsoft.com/en-us/azure/devops/pipelines/process/templates)
- [Define variables and variable groups](https://learn.microsoft.com/en-us/azure/devops/pipelines/process/variables)
