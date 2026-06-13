/**
 * Typed client for the Athenaeum backend.
 *
 * Base URL comes from NEXT_PUBLIC_API_BASE_URL (exposed to the browser) and
 * defaults to the local FastAPI dev server. No secrets here — public config only.
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface PingResponse {
  message: string;
  service: string;
  version: string;
  timestamp: string;
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

/** Call the backend connectivity endpoint. Throws on non-2xx or network failure. */
export async function pingBackend(
  signal?: AbortSignal,
): Promise<PingResponse> {
  const response = await fetch(`${API_BASE_URL}/api/ping`, {
    signal,
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    throw new Error(`Backend ping failed: ${response.status}`);
  }

  return (await response.json()) as PingResponse;
}

// ── Learner workspace contracts (mirror the FastAPI response models) ──────────

export interface PersonaSummary {
  employee_id: string;
  codename: string;
  team_id: string;
  vertical: string;
  seniority: "senior" | "junior" | "manager";
  role_title: string;
  certification: string;
  is_manager: boolean;
  preferred_learning_slot: string;
}

export interface CatalogCourse {
  id: string;
  slug: string;
  title: string;
  summary: string;
  level: string;
  vertical: string;
  vertical_title: string;
  primary_cert: string;
}

/** Persisted assistant-turn artifacts, so the trace/choices/plan survive reload. */
export interface MessageMeta {
  phases?: PhaseTelemetry[];
  suggestion?: Suggestion | null;
  plan?: StudyPlan | null;
  pace_request?: PaceRequest | null;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  created_at?: string;
  meta?: MessageMeta;
}

export interface CourseSummary {
  id: string;
  persona_id: string;
  chat_name: string;
  catalog_id: string | null;
  status: number;
  updated_at: string;
}

export interface Course {
  id: string;
  persona_id: string;
  chat_name: string;
  catalog_id: string | null;
  catalog_title: string | null;
  status: number;
  messages: ChatMessage[];
  assessment_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface Assessment {
  id: string;
  type: "llm" | "choices";
  is_practice: boolean;
  created_at: string;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    throw new Error(`Request to ${path} failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

/** The 10 learner personas (managers excluded) for the account chooser. */
export function fetchLearners(signal?: AbortSignal): Promise<PersonaSummary[]> {
  return requestJson<PersonaSummary[]>(
    "/api/workiq/personas?learners_only=true",
    { signal },
  );
}

/** The 15 Athenaeum courses a chat may be linked to. */
export function fetchCatalog(signal?: AbortSignal): Promise<CatalogCourse[]> {
  return requestJson<CatalogCourse[]>("/api/catalog/courses", { signal });
}

/** A persona's chats (courses), most-recently-updated first. */
export function listCourses(
  personaId: string,
  signal?: AbortSignal,
): Promise<CourseSummary[]> {
  return requestJson<CourseSummary[]>(
    `/api/courses?persona_id=${encodeURIComponent(personaId)}`,
    { signal },
  );
}

/** Open a new chat (course); its name is generated from the first message. */
export function createCourse(
  personaId: string,
  content: string,
): Promise<Course> {
  return requestJson<Course>("/api/courses", {
    method: "POST",
    body: JSON.stringify({ persona_id: personaId, content }),
  });
}

export function getCourse(courseId: string, signal?: AbortSignal): Promise<Course> {
  return requestJson<Course>(`/api/courses/${courseId}`, { signal });
}

export interface CoursePatch {
  chat_name?: string;
  catalog_id?: string | null;
}

/** Rename a chat and/or (un)link its Athenaeum course. */
export function patchCourse(courseId: string, patch: CoursePatch): Promise<Course> {
  return requestJson<Course>(`/api/courses/${courseId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function listAssessments(
  courseId: string,
  signal?: AbortSignal,
): Promise<Assessment[]> {
  return requestJson<Assessment[]>(`/api/courses/${courseId}/assessments`, {
    signal,
  });
}

// ── Agent pipeline event protocol (mirrors app/agent/contracts.py) ────────────

export type Route =
  | "greeting"
  | "recommend"
  | "study_plan"
  | "foundry_iq"
  | "work_iq"
  | "general";

export interface GroundingSource {
  ref: string;
  title: string;
  snippet: string;
  kind: "course" | "work" | "catalog";
  url: string | null;
}

export interface PhaseTelemetry {
  phase: "injection_gate" | "router" | "answer";
  status: "running" | "passed" | "blocked" | "error";
  summary: string;
  reasoning: string;
  provider: string | null;
  model: string | null;
  tier: number | null;
  latency_ms: number | null;
  route: Route | null;
  sources: GroundingSource[];
}

export interface CourseSuggestion {
  catalog_id: string;
  title: string;
  cert: string;
  level: string;
  pitch: string;
  reason: string;
  prep_points: string[];
}

/** One or more courses the learner can choose from (the course-selection tool). */
export interface Suggestion {
  prompt: string;
  options: CourseSuggestion[];
}

// ── Study plan (calendar-grounded, module-level) ──────────────────────────────

export type Pace = "slower" | "normal" | "faster";

export interface StudySession {
  day: string;
  slot: string;
  start: string;
  end: string;
  duration_minutes: number;
  source: string;
}

export interface ScheduledBlock {
  week: number;
  day: string;
  start: string;
  end: string;
  minutes: number;
}

export interface ModulePlan {
  module_id: string;
  title: string;
  sequence: number;
  estimated_minutes: number;
  scheduled: ScheduledBlock[];
  complete_before: string;
  objectives: string[];
}

export interface StudyPlan {
  catalog_id: string;
  title: string;
  cert: string;
  pace: Pace;
  weekly_study_hours: number;
  total_hours: number;
  weeks: number;
  start_date: string;
  modules: ModulePlan[];
  sessions: StudySession[];
  capacity_reason: string;
}

export interface PaceRequest {
  catalog_id: string;
  title: string;
  prompt: string;
  options: Pace[];
}

export type PipelineEvent =
  | { type: "phase"; phase: PhaseTelemetry }
  | { type: "token"; token: string }
  | { type: "suggestion"; prompt: string; options: CourseSuggestion[] }
  | { type: "plan"; plan: StudyPlan }
  | { type: "pace_request"; catalog_id: string; title: string; prompt: string; options: Pace[] }
  | { type: "blocked"; reason: string }
  | { type: "error"; message: string }
  | { type: "done"; route: Route | null; suggested: boolean };

export interface StreamHandlers {
  onPhase?: (phase: PhaseTelemetry) => void;
  onToken?: (token: string) => void;
  onSuggestion?: (suggestion: Suggestion) => void;
  onPlan?: (plan: StudyPlan) => void;
  onPaceRequest?: (request: PaceRequest) => void;
  onBlocked?: (reason: string) => void;
  onError?: (message: string) => void;
  onDone?: (info: { route: Route | null; suggested: boolean }) => void;
}

/**
 * Send a message and stream the full agent pipeline over SSE.
 *
 * Dispatches each typed pipeline event to the matching handler. The backend
 * persists both turns; the caller drives live UI (phase trace, tokens, the
 * course suggestion, a blocked toast, or an explicit error).
 */
export async function streamMessage(
  courseId: string,
  content: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/courses/${courseId}/messages`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ content }),
      signal,
    },
  );
  if (!response.ok || !response.body) {
    throw new Error(`Message stream failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE events are separated by a blank line; keep the trailing partial chunk.
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const event of events) {
      const line = event.trim();
      if (!line.startsWith("data:")) continue;
      const payload = JSON.parse(line.slice(5).trim()) as PipelineEvent;
      dispatchEvent(payload, handlers);
    }
  }
}

function dispatchEvent(event: PipelineEvent, handlers: StreamHandlers): void {
  switch (event.type) {
    case "phase":
      handlers.onPhase?.(event.phase);
      break;
    case "token":
      handlers.onToken?.(event.token);
      break;
    case "suggestion":
      handlers.onSuggestion?.({ prompt: event.prompt, options: event.options });
      break;
    case "plan":
      handlers.onPlan?.(event.plan);
      break;
    case "pace_request":
      handlers.onPaceRequest?.({
        catalog_id: event.catalog_id,
        title: event.title,
        prompt: event.prompt,
        options: event.options,
      });
      break;
    case "blocked":
      handlers.onBlocked?.(event.reason);
      break;
    case "error":
      handlers.onError?.(event.message);
      break;
    case "done":
      handlers.onDone?.({ route: event.route, suggested: event.suggested });
      break;
  }
}

/** Accept a suggested course: link it to this chat and start attempt 1. */
export function acceptCourse(courseId: string, catalogId: string): Promise<Course> {
  return requestJson<Course>(`/api/courses/${courseId}/accept`, {
    method: "POST",
    body: JSON.stringify({ catalog_id: catalogId }),
  });
}

/** Set the study pace (gates plan generation). */
export function setPace(courseId: string, pace: Pace): Promise<Course> {
  return requestJson<Course>(`/api/courses/${courseId}/pace`, {
    method: "POST",
    body: JSON.stringify({ pace }),
  });
}

// ── Modules (the study plan's progress) ───────────────────────────────────────

export interface CourseModuleProgress {
  module_id: string;
  title: string;
  sequence: number;
  estimated_minutes: number;
  complete_before: string;
  completed: boolean;
  locked: boolean;
  scheduled: ScheduledBlock[];
}

export interface ModuleContent {
  module_id: string;
  title: string;
  content: string;
}

/** The course's scheduled modules with progress + sequential lock state. */
export function listModules(
  courseId: string,
  signal?: AbortSignal,
): Promise<CourseModuleProgress[]> {
  return requestJson<CourseModuleProgress[]>(`/api/courses/${courseId}/modules`, { signal });
}

/** A module's markdown content for the Modules tab. */
export function getModuleContent(
  courseId: string,
  moduleId: string,
  signal?: AbortSignal,
): Promise<ModuleContent> {
  return requestJson<ModuleContent>(
    `/api/courses/${courseId}/modules/${moduleId}/content`,
    { signal },
  );
}

/** Mark a module complete (sequential — only the active module). */
export function completeModule(
  courseId: string,
  moduleId: string,
): Promise<CourseModuleProgress[]> {
  return requestJson<CourseModuleProgress[]>(
    `/api/courses/${courseId}/modules/${moduleId}/complete`,
    { method: "POST" },
  );
}
