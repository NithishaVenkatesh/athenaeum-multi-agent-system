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
export async function pingBackend(signal?: AbortSignal): Promise<PingResponse> {
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

/** A "one course per chat" steer: this chat is locked, open a new one to switch. */
export interface NewChat {
  prompt: string;
  current_title: string | null;
  /** When set, the course already lives in this chat — open it instead of forking. */
  target_course_id?: string | null;
  target_title?: string | null;
}

/** Persisted assistant-turn artifacts, so the trace/choices/plan survive reload. */
export interface MessageMeta {
  phases?: PhaseTelemetry[];
  suggestion?: Suggestion | null;
  plan?: StudyPlan | null;
  pace_request?: PaceRequest | null;
  skill_gate?: SkillGateRequest | null;
  skill_result?: SkillResult | null;
  new_chat?: NewChat | null;
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
  updated_at: string;
}

export interface Course {
  id: string;
  persona_id: string;
  chat_name: string;
  catalog_id: string | null;
  catalog_title: string | null;
  messages: ChatMessage[];
  assessment_ids: string[];
  /** The open skill-check quiz, if one is in progress — used to restore the card. */
  skill_check_active?: SkillCheck | null;
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

export function getCourse(
  courseId: string,
  signal?: AbortSignal,
): Promise<Course> {
  return requestJson<Course>(`/api/courses/${courseId}`, { signal });
}

export interface CoursePatch {
  chat_name?: string;
  catalog_id?: string | null;
}

/** Rename a chat and/or (un)link its Athenaeum course. */
export function patchCourse(
  courseId: string,
  patch: CoursePatch,
): Promise<Course> {
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
  | "upcoming"
  | "general";

export interface GroundingSource {
  ref: string;
  title: string;
  snippet: string;
  kind: "course" | "work" | "catalog";
  url: string | null;
}

/** One sub-step within a pipeline phase (gate layers, router decision, …). */
export interface TraceStep {
  label: string;
  /** true=passed, false=blocked, null=informational (unavailable/skipped) */
  passed: boolean | null;
  detail: string;
  model: string | null;
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
  /** Course state at this turn (the state-graph node the router conditioned on). */
  state: string | null;
  sources: GroundingSource[];
  steps: TraceStep[];
  confidence: number | null;
  off_topic: number | null;
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
  base_minutes: number;
  pace_minutes: number;
  skill_delta: number;
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
  total_base_hours: number;
  total_pace_hours: number;
  weeks: number;
  start_date: string;
  modules: ModulePlan[];
  sessions: StudySession[];
  capacity_reason: string;
  balloon_warning: string | null;
  awaiting_approval: boolean;
}

export interface PaceRequest {
  catalog_id: string;
  title: string;
  prompt: string;
  options: Pace[];
}

export interface SkillGateRequest {
  catalog_id: string;
  title: string;
  prompt: string;
  options: string[]; // ["fresher", "assessment"]
}

export interface SkillCheckQuestion {
  id: string;
  prompt: string;
  kind: "mcq" | "msq";
  choices: string[];
}

export interface SkillCheckModule {
  module_id: string;
  title: string;
  questions: SkillCheckQuestion[];
}

export interface SkillCheck {
  catalog_id: string;
  title: string;
  modules: SkillCheckModule[];
}

export interface SkillModuleScore {
  module_id: string;
  title: string;
  correct: number;
  total: number;
  fraction: number;
}

export interface SkillResult {
  catalog_id: string;
  overall_fraction: number;
  modules: SkillModuleScore[];
  fresher: boolean;
}

export interface SkillAnswer {
  module_id: string;
  question_id: string;
  selections: string[];
}

export type PipelineEvent =
  | { type: "phase"; phase: PhaseTelemetry }
  | { type: "token"; token: string }
  | { type: "suggestion"; prompt: string; options: CourseSuggestion[] }
  | { type: "plan"; plan: StudyPlan }
  | {
      type: "pace_request";
      catalog_id: string;
      title: string;
      prompt: string;
      options: Pace[];
    }
  | {
      type: "skill_gate_request";
      catalog_id: string;
      title: string;
      prompt: string;
      options: string[];
    }
  | {
      type: "new_chat";
      prompt: string;
      current_title: string | null;
      target_course_id?: string | null;
      target_title?: string | null;
    }
  | { type: "blocked"; reason: string }
  | { type: "error"; message: string }
  | { type: "done"; route: Route | null; suggested: boolean };

export interface StreamHandlers {
  onPhase?: (phase: PhaseTelemetry) => void;
  onToken?: (token: string) => void;
  onSuggestion?: (suggestion: Suggestion) => void;
  onPlan?: (plan: StudyPlan) => void;
  onPaceRequest?: (request: PaceRequest) => void;
  onSkillGate?: (request: SkillGateRequest) => void;
  onNewChat?: (newChat: NewChat) => void;
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
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
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
    case "skill_gate_request":
      handlers.onSkillGate?.({
        catalog_id: event.catalog_id,
        title: event.title,
        prompt: event.prompt,
        options: event.options,
      });
      break;
    case "new_chat":
      handlers.onNewChat?.({
        prompt: event.prompt,
        current_title: event.current_title,
        target_course_id: event.target_course_id,
        target_title: event.target_title,
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

/**
 * Stream grounded feedback on the learner's latest quiz/oral attempt for a module.
 *
 * This is the "Get Feedback" button's path. Unlike a normal chat message it does
 * NOT run through the topic gate (a bare "why did I fail" question has none of the
 * module's vocabulary, so grounding rejects it and the answer is refused). The
 * backend grounds on the module's own material plus the learner's actual answers
 * and persists both turns, so the same phase/token/done events apply here.
 */
export async function streamFeedback(
  courseId: string,
  moduleId: string,
  kind: AssessmentType,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/courses/${courseId}/modules/${moduleId}/feedback?type=${kind}`,
    { method: "POST", headers: { Accept: "text/event-stream" }, signal },
  );
  if (!response.ok || !response.body) {
    throw new Error(`Feedback stream failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
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

/** Accept a suggested course: link it to this chat and start attempt 1. */
export function acceptCourse(
  courseId: string,
  catalogId: string,
): Promise<Course> {
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

/** Sample the multi-tab skill check (up to 4 questions per module). */
export function startSkillCheck(courseId: string): Promise<SkillCheck> {
  return requestJson<SkillCheck>(`/api/courses/${courseId}/skill/start`, {
    method: "POST",
  });
}

/** Grade the skill check; stores per-module scores and posts a transcript message. */
export function gradeSkillCheck(
  courseId: string,
  answers: SkillAnswer[],
): Promise<SkillResult> {
  return requestJson<SkillResult>(`/api/courses/${courseId}/skill/grade`, {
    method: "POST",
    body: JSON.stringify({ answers }),
  });
}

/** Skip the check as a fresher (score 0 on every module). */
export function skillFresher(courseId: string): Promise<SkillResult> {
  return requestJson<SkillResult>(`/api/courses/${courseId}/skill/fresher`, {
    method: "POST",
  });
}

/** Set or clear the optional target deadline. */
export async function setDeadline(
  courseId: string,
  deadline: string | null,
): Promise<void> {
  await fetch(`${API_BASE_URL}/api/courses/${courseId}/deadline`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ deadline }),
  });
}

/** Approve the staged plan: write its modules + deadlines. */
export function approvePlan(courseId: string): Promise<CourseModuleProgress[]> {
  return requestJson<CourseModuleProgress[]>(
    `/api/courses/${courseId}/plan/approve`,
    { method: "POST" },
  );
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
  return requestJson<CourseModuleProgress[]>(
    `/api/courses/${courseId}/modules`,
    { signal },
  );
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

// ── Evaluations (the canonical per-module set: a quiz + an oral each) ──────────

/** One of a course's evaluations (two per module) with lock + latest-attempt score. */
export interface Evaluation {
  module_id: string;
  module_title: string;
  sequence: number;
  type: AssessmentType;
  locked: boolean;
  completed: boolean;
  attempted: boolean;
  score: number | null;
  passed: boolean | null;
  attempts_to_pass: number | null;
  review_assessment_id: string | null;
  attempts: number;
}

/** The course's full evaluation set (2 per module), ordered and lock-aware. */
export function listEvaluations(
  courseId: string,
  signal?: AbortSignal,
): Promise<Evaluation[]> {
  return requestJson<Evaluation[]>(`/api/courses/${courseId}/evaluations`, {
    signal,
  });
}

// ── Assessment session types ───────────────────────────────────────────────────

export type AssessmentType = "choices" | "llm";

export interface SessionChoiceQuestion {
  id: string;
  bank_question_id: string | null;
  sequence: number;
  prompt: string;
  kind: "mcq" | "msq";
  choices: string[];
  learner_choice: string[] | null;
  submitted: boolean;
  is_correct: boolean | null;
}

export interface SessionLlmQuestion {
  id: string;
  bank_question_id: string | null;
  prompt: string;
  messages: Array<{ role: string; content: string }>;
  submitted: boolean;
  score: number | null;
  reasoning: string | null;
  turn_count: number;
  grading_complete: boolean;
}

export interface AssessmentSession {
  id: string;
  course_id: string;
  module_id: string | null;
  type: AssessmentType;
  attempt_number: number;
  score: number | null;
  passed: boolean | null;
  completed_at: string | null;
  created_at: string;
  choice_questions: SessionChoiceQuestion[];
  llm_questions: SessionLlmQuestion[];
}

export interface ModuleAssessmentSummary {
  id: string;
  type: AssessmentType;
  attempt_number: number;
  score: number | null;
  passed: boolean | null;
  attempts_to_pass: number | null;
  completed_at: string | null;
  created_at: string;
}

export interface ChoiceQuestionResult {
  id: string;
  sequence: number;
  prompt: string;
  kind: "mcq" | "msq";
  choices: string[];
  correct_answers: string[];
  learner_choice: string[] | null;
  is_correct: boolean | null;
}

export interface ChoiceSubmitResult {
  assessment_id: string;
  score: number;
  passed: boolean;
  questions: ChoiceQuestionResult[];
}

export interface LlmQuestionResult {
  id: string;
  prompt: string;
  score: number | null;
  reasoning: string | null;
  turn_count: number;
  grading_complete: boolean;
  messages: Array<{ role: string; content: string }>;
}

export interface LlmSubmitResult {
  assessment_id: string;
  score: number;
  passed: boolean;
  questions: LlmQuestionResult[];
}

export type LlmGraderEvent =
  | { type: "token"; token: string }
  | { type: "grade"; score: number; reasoning: string }
  | { type: "error"; message: string }
  | { type: "done" };

export interface LlmGraderHandlers {
  onToken?: (token: string) => void;
  onGrade?: (score: number, reasoning: string) => void;
  onError?: (message: string) => void;
  onDone?: () => void;
}

// ── Assessment session API calls ──────────────────────────────────────────────

/**
 * Start a new choices or LLM assessment session for a module.
 *
 * Pass `force` to retake an assessment already passed (the Evaluations tab's
 * Retake action) — the backend samples a fresh question set and persists it.
 */
export function startAssessment(
  courseId: string,
  moduleId: string,
  type: AssessmentType,
  force = false,
): Promise<AssessmentSession> {
  const query = force ? `?type=${type}&force=true` : `?type=${type}`;
  return requestJson<AssessmentSession>(
    `/api/courses/${courseId}/modules/${moduleId}/assessments/start${query}`,
    { method: "POST" },
  );
}

/** All assessment attempts for a module (for the summary list). */
export function listModuleAssessments(
  courseId: string,
  moduleId: string,
  signal?: AbortSignal,
): Promise<ModuleAssessmentSummary[]> {
  return requestJson<ModuleAssessmentSummary[]>(
    `/api/courses/${courseId}/modules/${moduleId}/assessments`,
    { signal },
  );
}

/** Full state of one assessment session. */
export function getAssessmentSession(
  courseId: string,
  assessmentId: string,
  signal?: AbortSignal,
): Promise<AssessmentSession> {
  return requestJson<AssessmentSession>(
    `/api/courses/${courseId}/assessments/${assessmentId}`,
    { signal },
  );
}

/** Save the learner's in-progress selection for one choice question. */
export function selectChoiceAnswer(
  courseId: string,
  assessmentId: string,
  questionId: string,
  selections: string[],
): Promise<SessionChoiceQuestion> {
  return requestJson<SessionChoiceQuestion>(
    `/api/courses/${courseId}/assessments/${assessmentId}/choices/${questionId}/select`,
    { method: "POST", body: JSON.stringify({ selections }) },
  );
}

/** Submit the choices assessment and get graded results. */
export function submitChoices(
  courseId: string,
  assessmentId: string,
): Promise<ChoiceSubmitResult> {
  return requestJson<ChoiceSubmitResult>(
    `/api/courses/${courseId}/assessments/${assessmentId}/choices/submit`,
    { method: "POST" },
  );
}

/** Get the revealed results for a submitted assessment. */
export function getAssessmentResults(
  courseId: string,
  assessmentId: string,
  signal?: AbortSignal,
): Promise<ChoiceSubmitResult | LlmSubmitResult> {
  return requestJson<ChoiceSubmitResult | LlmSubmitResult>(
    `/api/courses/${courseId}/assessments/${assessmentId}/results`,
    { signal },
  );
}

/** Get the grader's opening message for the current LLM question. */
export function startLlmQuestion(
  courseId: string,
  assessmentId: string,
): Promise<SessionLlmQuestion> {
  return requestJson<SessionLlmQuestion>(
    `/api/courses/${courseId}/assessments/${assessmentId}/llm/start`,
    { method: "POST" },
  );
}

/**
 * Send one learner turn to the LLM grader over SSE.
 * Dispatches token/grade/error/done events to handlers.
 */
export async function sendLlmTurn(
  courseId: string,
  assessmentId: string,
  questionId: string,
  content: string,
  handlers: LlmGraderHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/courses/${courseId}/assessments/${assessmentId}/llm/${questionId}/turn`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({ content }),
      signal,
    },
  );
  if (!response.ok || !response.body) {
    throw new Error(`LLM turn stream failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const raw of events) {
      const line = raw.trim();
      if (!line.startsWith("data:")) continue;
      const event = JSON.parse(line.slice(5).trim()) as LlmGraderEvent;
      dispatchGraderEvent(event, handlers);
    }
  }
}

function dispatchGraderEvent(
  event: LlmGraderEvent,
  handlers: LlmGraderHandlers,
): void {
  switch (event.type) {
    case "token":
      handlers.onToken?.(event.token);
      break;
    case "grade":
      handlers.onGrade?.(event.score, event.reasoning);
      break;
    case "error":
      handlers.onError?.(event.message);
      break;
    case "done":
      handlers.onDone?.();
      break;
  }
}

/** Submit the LLM assessment (all questions must be graded). */
export function submitLlm(
  courseId: string,
  assessmentId: string,
): Promise<LlmSubmitResult> {
  return requestJson<LlmSubmitResult>(
    `/api/courses/${courseId}/assessments/${assessmentId}/llm/submit`,
    { method: "POST" },
  );
}

// ── Notifications + streak (mirror app/notifications/schemas.py) ──────────────

export type NotificationKind =
  | "next_module"
  | "course_complete"
  | "deadline_soon"
  | "deadline_missed";

/** One notification as rendered in the panel and as a live toast. */
export interface NotificationItem {
  id: string;
  course_id: string;
  module_id: string | null;
  kind: NotificationKind;
  title: string;
  body: string;
  /** Frontend deep link, e.g. "/chat/<course>/modules/<module>". */
  link: string;
  read: boolean;
  toasted: boolean;
  created_at: string;
}

/** The persona's gamification score behind the fire button. */
export interface StreakSummary {
  persona_id: string;
  points: number;
  on_time_streak: number;
  miss_streak: number;
}

/** The single poll payload: notifications + unread badge count + streak. */
export interface NotificationFeed {
  notifications: NotificationItem[];
  unread_count: number;
  streak: StreakSummary;
}

/** Poll a persona's notifications + streak (the backend ticks lazily on read). */
export function fetchNotifications(
  personaId: string,
  signal?: AbortSignal,
): Promise<NotificationFeed> {
  return requestJson<NotificationFeed>(
    `/api/notifications?persona_id=${encodeURIComponent(personaId)}`,
    { signal },
  );
}

/** Acknowledge one notification (clears it from the unread badge). */
export function markNotificationRead(
  notificationId: string,
): Promise<NotificationItem> {
  return requestJson<NotificationItem>(
    `/api/notifications/${notificationId}/read`,
    { method: "POST" },
  );
}

/** Mark every notification for a persona as read. */
export function markAllNotificationsRead(
  personaId: string,
): Promise<{ changed: number }> {
  return requestJson<{ changed: number }>(
    `/api/notifications/read-all?persona_id=${encodeURIComponent(personaId)}`,
    { method: "POST" },
  );
}

/** Flag notifications already surfaced as live toasts (so polling won't re-toast). */
export function markNotificationsToasted(
  ids: string[],
): Promise<{ changed: number }> {
  return requestJson<{ changed: number }>("/api/notifications/toasted", {
    method: "POST",
    body: JSON.stringify({ ids }),
  });
}
