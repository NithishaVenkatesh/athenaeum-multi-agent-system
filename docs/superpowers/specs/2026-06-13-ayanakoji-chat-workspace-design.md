# Ayanakoji Chat / Course Workspace — Design

**Date:** 2026-06-13
**Status:** Approved — in implementation
**Branch:** `feat/ayanakoji-chat-workspace`

## Goal

Add a learner-facing workspace to Ayanakoji: a persona "sign in", then a ChatGPT-style
interface where **a chat _is_ a course**. Two pages per course — Chat and Assessments.
Backed by a new SQLite persistence layer; chat replies stream from Foundry's cheapest
model, with a deterministic offline fallback so the whole app runs and tests green
without Azure credentials.

## Decisions (locked)

- **Auth** = persona selection only. Picking a learner persona is the session; the
  `employee_id` persists in `localStorage`. No passwords. Sign out clears it.
- **DB** = SQLite + SQLModel. `create_all` on startup (no Alembic). Tests use a temp DB.
- **Chat naming** = first message → short title via the cheap model (offline: truncation).
- **Responses** = SSE streaming (token-by-token).
- **UI** = shadcn/ui components used extensively; framer-motion easing per
  `/emil-design-eng`; visual quality per `/impeccable` + `/ui-ux-pro-max`.
- **Avatars** = DiceBear `notionists-neutral`, generated locally from `@dicebear/core` +
  `@dicebear/collection`, deterministically seeded by codename (no network / CSP-safe).
- **Personas** = pulled live from the existing backend, filtered to learners
  (Polaris / manager excluded server-side).

## Routes (Next.js App Router)

- `/login` — persona chooser, framed as "Sign in to your account". Grid of the 10 learner
  personas; card = avatar + codename + `employee_id` + role/vertical. Select → store →
  `/chat`.
- `/` — client redirect: persona ? `/chat` : `/login`.
- `/chat` — shell, "new chat" state (no course). Composer active; **no** Assessments switch.
- `/chat/[courseId]` — existing chat: message thread + composer + Chat|Assessments switcher.
- `/chat/[courseId]/assessments` — designed empty-state placeholder + switcher.

Shared `/chat` layout: top-left searchable course chooser (+ "New chat"); top-center
page switcher (only with a real `courseId`); top-right persona avatar + Sign out.

## Data model (SQLite + SQLModel)

- **course** (the chat = course record): `id` (uuid hex), `persona_id` (index),
  `chat_name` (editable, LLM-derived), `course_id` (nullable; athenaeum catalog id,
  validated ∈ the 15 only when set), `status` (int — `0`=just started, `+N`=on attempt N,
  `-N`=passed on attempt N), `messages` (JSON array of `{role, content, created_at}` —
  stored inline, no separate table), `created_at`, `updated_at`.
- **assessment**: `id`, `course_id` (FK), `type` (`llm`|`choices`), `is_practice`
  (bool — true=practice, false=evaluation), `created_at`.
- **choice_question**: `id`, `assessment_id` (FK), `prompt`, `choices` (JSON),
  `correct_answers` (JSON), `learner_choice` (JSON, nullable), `submitted` (bool),
  `is_correct` (bool, nullable).
- **llm_question**: `id`, `assessment_id` (FK), `prompt`, `messages` (JSON, seeded with
  the question), `submitted` (bool), `is_correct` (bool, nullable).

Assessment + question tables are modeled and created now (no UI populates them yet).
Messages are mutated immutably (reassign a new list) so SQLAlchemy tracks the change.

## Backend API

- `GET /api/workiq/personas?learners_only=true` — tested filter; excludes managers.
- `GET /api/catalog/courses` — flattened list of the 15 athenaeum courses (id, title,
  vertical, level, summary, primary_cert) for linking + validation.
- `POST /api/courses` `{persona_id, content}` → create course, `chat_name` = title(content),
  `status=0`, `course_id=null`. Returns the course (no message saved here).
- `GET /api/courses?persona_id=…` → summaries for the chooser.
- `GET /api/courses/{id}` → full course + messages + assessment_ids.
- `PATCH /api/courses/{id}` `{chat_name?, course_id?}` → rename / link course (validates id).
- `POST /api/courses/{id}/messages` `{content}` → **SSE**: append user message, stream
  assistant tokens over history, persist assistant message at end.
- `GET /api/courses/{id}/assessments` → `[]` for now (schema-backed).

## Offline LLM fallback

`app/courses/service.py` owns `generate_title()` and `stream_reply()`. When Foundry is
unconfigured or `OFFLINE_LLM=true`, both use a deterministic stub (truncated title /
echo-style stream). The live branch calls Azure OpenAI through an injectable
`client_factory` (default `app.foundry.build_openai_client`) so tests cover both paths
with a fake factory — no Azure needed. Makes dev, CI, E2E, and smoke runs fully offline.

## Testing

- **Backend (pytest, ≥80%):** model/schema round-trips incl. `status`, `submitted`,
  `is_correct`, `is_practice`; catalog loader + endpoint; learners filter; course
  create (title mocked + offline) / list / get / rename / link-validation; messages
  append + SSE stream persists assistant message (fake client_factory); empty assessments.
- **Frontend (Vitest + RTL):** chooser shows learners only (no Polaris) with ids + avatars;
  deterministic avatar util; persona guard/redirect; searchable course chooser + "new chat";
  composer (new-chat creates then streams; existing streams) with api/SSE mocked; inline
  rename; switcher visibility rule; sign-out; assessments empty state.
- **E2E (Playwright, offline):** land → choose persona → send → record created + reply
  streamed → rename → switch to assessments → sign out.

## CI/CD

Existing backend/frontend jobs cover the new code. Set `OFFLINE_LLM=true` for the
Playwright `webServer` + E2E CI step; add `@dicebear/*` to the lockfile; add
`DATABASE_URL`, `OFFLINE_LLM`, `ATHENAEUM_CATALOG_PATH` to `.env(.local).example`. SQLite
needs no CI infra.
