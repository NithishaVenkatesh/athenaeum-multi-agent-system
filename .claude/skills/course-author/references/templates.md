# Athenaeum document templates

Two file types. Follow the structure exactly; the ingestion pipeline parses the frontmatter
and the section headings, so deviations break indexing.

---

## 1. `course.md` — course overview

````markdown
---
kind: course
id: <course-id>            # e.g. cb-c01
vertical: <vertical-id>    # e.g. cloud-backend
course_id: <course-id>     # same as id
title: <Course title>
level: foundational|intermediate|advanced
grounded_on: "<CERT> skills outline (<date>), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/.../study-guides/<cert>
synthetic: true
prereqs: [<course-id>, ...]    # prerequisite course ids (may be empty)
objectives: []                 # leave empty for course overview
---

# <Course title>

<Lead paragraph: the real capability this course builds and who needs it. 2–4 sentences,
concrete, no fluff.>

## Who this is for

<2–4 sentences: the role/experience assumed, and the prerequisite courses by title.>

## What you'll be able to do

- <Outcome-verb bullet>
- <…> (4–6 bullets, course-level outcomes)

## Module path

This course is four sequential modules; each builds on the last.

1. **<Module 1 title>** — <one line>
2. **<Module 2 title>** — <one line>
3. **<Module 3 title>** — <one line>
4. **<Module 4 title>** — <one line>

## Prerequisites

<Concrete prior knowledge + named prerequisite courses, or "None — this is an entry point
for the vertical.">

## How this fits the bigger picture

<3–5 sentences connecting the course to the vertical and to real Azure work.>
````

Target length: **600–900 words.**

---

## 2. `module-NN-<slug>.md` — teaching module

`NN` is the zero-padded order (`01`–`04`); `<slug>` is a short kebab-case title.

````markdown
---
kind: module
id: <module-id>            # e.g. cb-c01-m02
vertical: <vertical-id>
course_id: <course-id>
title: <Module title>
level: foundational|intermediate|advanced
grounded_on: "<CERT> skills outline (<date>), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/.../study-guides/<cert>
synthetic: true
order: <1-4>
prereqs: [<module-id or course-id>, ...]
objectives:
  - <objective 1>
  - <objective 2>
  - <objective 3>
---

# <Module title>

<Lead paragraph: the real problem the learner cannot yet solve, in a fictional but
believable scenario. Make them want the skill. No "in this module we will".>

## Learning objectives

By the end of this module you will be able to:

- <Outcome-verb objective>
- <…> (3–5 total)

## Concepts

### <Concept subsection 1>

<Substantive explanation: mechanism + why. Teach the model of how it works.>

### <Concept subsection 2>

<…> (2–4 `###` subsections; this is the longest part of the module.)

## Walkthrough: <fictional scenario name>

<Narrate a concrete task end to end in a fictional org. Explain each step.>

```python
# At least one correct, runnable, idiomatic block (python/csharp/bicep/yaml/kql/bash).
```

<Explain what the code did and what to observe.>

## Common pitfalls

- **<Pitfall>** — <why it happens and how to avoid it.>
- <…> (3–5 total)

## Knowledge check

1. <Application/understanding question.>
2. <…>
3. <…>

<details>
<summary>Answers</summary>

1. <Answer> — <one-line rationale.>
2. <Answer> — <rationale.>
3. <Answer> — <rationale.>

</details>

## Summary

<3–5 sentences consolidating the mental model and naming the next module.>

## Further learning

- [<Real doc title>](https://learn.microsoft.com/...)
- <2–4 real public learn.microsoft.com links for the services taught.>
````

Target length: **900–1500 words of prose** (excluding code blocks).

---

## Slug and id conventions

- Vertical ids: `cloud-backend`, `devops-platform`, `data-engineering`, `ai-ml`,
  `architecture-security`.
- Course id: `<vertical-prefix>-c<NN>` (prefixes: `cb`, `do`, `de`, `ai`, `as`).
- Module id: `<course-id>-m<NN>`.
- Module filename: `module-<NN>-<short-slug>.md` inside the course directory.
- Course directory: `content/<vertical-id>/<course-slug>/`.

## Quality reminders

- Original prose only — no copied outline text.
- Fictional scenarios/orgs/data, obviously not real.
- Accurate service behavior; verify-in-docs framing for brittle specifics.
- Every module is a self-contained, citable chunk.
