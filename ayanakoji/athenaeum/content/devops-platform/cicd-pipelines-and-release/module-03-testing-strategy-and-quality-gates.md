---
kind: module
id: do-c02-m03
vertical: devops-platform
course_id: do-c02
title: Testing strategy and quality gates
level: intermediate
grounded_on: "AZ-400 skills outline (2026-04-24), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-400
synthetic: true
order: 3
prereqs: [do-c02-m01]
objectives:
  - Design a layered testing strategy in pipelines
  - Implement quality and release gates
  - Integrate code coverage analysis
---

# Testing strategy and quality gates

Larkspur Robotics has a pipeline that builds and ships, and packages that are versioned and reproducible. What it does not have is a way to *stop* a bad change. Last sprint, a refactor of the `order-service` pricing logic passed its build, sailed through to staging, and was caught only when a human happened to place a test order and saw a negative total. The pipeline did exactly what it was told — it just was not told to be skeptical. Your task is to make the pipeline earn its trust: layer the tests so failures surface fast, measure how much of the code those tests actually exercise, and put gates between stages that refuse to promote a build until objective conditions are met.

## Learning objectives

By the end of this module you will be able to:

- Design a layered testing strategy spanning local, unit, integration, and load tests, and place each layer where it pays off.
- Implement quality gates within a pipeline and approval/automatic release gates between stages, including security and governance checks.
- Integrate code-coverage analysis and interpret it without being misled by the percentage.

## Concepts

### The testing pyramid, and where each layer belongs

Tests trade speed for realism. The classic shape that balances them is a pyramid. At the wide base are **unit tests**: fast, isolated, no network or database, exercising one function or class. You can run thousands in seconds, so they belong early — ideally on the developer's machine before commit (the "local tests" tier) and again as the first job in the pipeline, so a broken unit fails in under a minute. Above them sit **integration tests**, which check that components actually talk to each other: the service against a real database, a queue, a downstream API. They are slower and need provisioned dependencies, so they run later in the pipeline, after units pass. At the narrow top are **load tests**, which validate behavior under realistic traffic; they are expensive and run least often, often on a schedule or before a major release rather than on every commit.

The reason the shape is a pyramid and not a rectangle is economic. A bug caught by a unit test costs seconds; the same bug caught by a load test costs a provisioned environment and a long run; caught in production it costs an incident. You push detection down and left. A team that inverts the pyramid — mostly slow end-to-end tests, few unit tests — gets a pipeline that is slow, flaky, and expensive, and developers learn to ignore it.

### Coverage: a useful signal, a terrible target

**Code coverage** measures which lines or branches your tests execute. Integrated into the pipeline, it answers "is this code path tested at all?" and is excellent for catching the pricing refactor that shipped with *zero* tests touching the new branch. But coverage measures execution, not assertion: a test can run a line and assert nothing meaningful about it. Ninety percent coverage with weak assertions catches less than sixty percent with sharp ones. So treat coverage as a *floor and a trend* — fail the build if coverage on changed code drops below a threshold, watch the direction over time — but never let "raise the number" become the goal, because the cheapest way to raise it is to write tests that assert nothing.

### Quality gates versus release gates

Two different mechanisms, often confused. A **quality gate** is a condition inside the pipeline that a build must satisfy to continue: tests green, coverage above threshold, no high-severity vulnerabilities from a security scan, linting clean. It is automatic and pass/fail. A **release gate** sits *between* stages and guards promotion — for example, between "deploy to staging" and "deploy to production." Release gates come in two flavors: **approvals**, where a named human or group must sign off (governance, change control), and **automatic gates**, where the pipeline polls an external signal — a monitoring system reporting healthy error rates, a change-management ticket marked approved, a security scan with no open findings — and only proceeds when the signal is good. Quality gates keep bad builds from advancing; release gates keep good builds from advancing at the wrong time or without the right authority.

## Walkthrough: gating order-service on tests, coverage, and approval

Larkspur will rebuild the `order-service` pipeline so it runs unit tests with coverage, fails if coverage on the project falls below 80%, runs integration tests in a later stage, and requires a human approval before production. Here is the verify stage that produces and enforces coverage:

```yaml
stages:
  - stage: Verify
    jobs:
      - job: unit_tests
        pool: { vmImage: 'ubuntu-latest' }
        steps:
          - task: UseDotNet@2
            inputs: { packageType: sdk, version: '8.x' }
          # Collect coverage in Cobertura format while running unit tests
          - script: >
              dotnet test src/order-service/OrderService.csproj
              --collect:"XPlat Code Coverage"
              --logger trx
            displayName: 'Unit tests + coverage'
          - task: PublishCodeCoverageResults@2
            inputs:
              summaryFileLocation: '$(Agent.TempDirectory)/**/coverage.cobertura.xml'
            displayName: 'Publish coverage'
          # Fail the build if line coverage drops below the floor
          - task: BuildQualityChecks@9
            inputs:
              checkCoverage: true
              coverageType: 'lines'
              coverageThreshold: '80'
            displayName: 'Quality gate: coverage >= 80%'

  - stage: IntegrationTests
    dependsOn: Verify
    jobs:
      - job: integration
        pool: { vmImage: 'ubuntu-latest' }
        steps:
          - script: docker compose -f test/docker-compose.yml up -d
            displayName: 'Start test database + dependencies'
          - script: dotnet test test/Integration --logger trx
            displayName: 'Run integration tests'
```

The production stage is guarded not by YAML but by an **environment approval**. You define a `production` environment in the project and attach an approval check to it; the deployment job that targets that environment then pauses for human sign-off before any step runs:

```yaml
  - stage: DeployProduction
    dependsOn: IntegrationTests
    jobs:
      - deployment: deploy_prod
        environment: production    # approval check configured on this environment
        pool: { vmImage: 'ubuntu-latest' }
        strategy:
          runOnce:
            deploy:
              steps:
                - script: ./deploy.sh --env production
                  displayName: 'Deploy order-service to production'
```

Notice the division of labor. The coverage check is a *quality gate* — automatic, blocking the build the moment a poorly tested change appears, which is exactly what would have caught the pricing refactor. The production environment's approval is a *release gate* — the build is good, but a human decides *when* it goes out. The precise marketplace task versions (`BuildQualityChecks@9`, `PublishCodeCoverageResults@2`) and the way approvals and automatic gate checks are configured on environments evolve, so confirm the current task versions and environment-check options in the docs.

## Common pitfalls

- **Inverting the pyramid.** Leaning on slow end-to-end tests instead of fast unit tests makes the pipeline slow and flaky, so developers stop trusting and reading it. Put most of your test mass at the unit layer.
- **Treating coverage as a goal rather than a floor.** Chasing a high percentage invites assertion-free tests that execute lines but verify nothing. Gate on a floor and on the trend of changed-code coverage, and review assertion quality in code review.
- **Confusing quality gates with release gates.** A passing test suite does not mean a change should ship *now*; an approval does not mean the code is correct. Use automatic quality gates for correctness and release gates for timing and authority.
- **Running integration tests against shared mutable infrastructure.** Pointing integration tests at a long-lived shared database makes them order-dependent and flaky. Spin up disposable dependencies per run (e.g. containers) so each run starts clean.
- **No security or governance gate before production.** Shipping without a vulnerability scan or change-control check passes audits in name only. Wire security scanning as a quality gate and change approval as a release gate.

## Knowledge check

1. Your team's pipeline runs in 40 minutes because almost all tests are end-to-end, and developers have started ignoring red runs. What change to the test mix addresses both the speed and the trust problem?
2. A pull request raises coverage from 72% to 91%, yet a reviewer is uneasy. What is the most likely reason coverage can rise while real safety does not?
3. A build has green tests, 85% coverage, and a clean security scan, but it is a Friday afternoon and the on-call engineer wants to hold it until Monday. Which mechanism enforces that decision, and is it a quality gate or a release gate?

<details>
<summary>Answers</summary>

1. Shift most test mass to fast, isolated unit tests at the base of the pyramid and reserve end-to-end/load tests for fewer, later runs. Faster feedback both shortens the pipeline and restores trust. — Speed and reliability come from pushing detection down and left.
2. Coverage measures lines executed, not assertions made; the new tests may run code without meaningfully verifying it. — High coverage with weak assertions is a false signal.
3. An environment approval acting as a release gate — the build is good (quality gates passed), but a human controls *when* it deploys. — Release gates govern timing and authority, not correctness.

</details>

## Summary

A trustworthy pipeline is skeptical by design: a pyramid of fast unit, slower integration, and occasional load tests pushes failures down and left; coverage is a floor and a trend, never a target; and gates split cleanly into automatic quality gates that block bad builds and release gates (approvals and automatic checks) that govern when good builds advance. With Larkspur's pipeline now refusing to promote untested or unapproved changes, the final module, **Progressive deployment strategies**, ensures that even an approved change that turns out bad in production fails small.

## Further learning

- [Code coverage in Azure Pipelines](https://learn.microsoft.com/en-us/azure/devops/pipelines/test/review-code-coverage-results)
- [Define approvals and checks](https://learn.microsoft.com/en-us/azure/devops/pipelines/process/approvals)
- [Release gates and deployment controls](https://learn.microsoft.com/en-us/azure/devops/pipelines/release/approvals/gates)
- [Run automated tests in pipelines](https://learn.microsoft.com/en-us/azure/devops/pipelines/test/getting-started-with-continuous-testing)
