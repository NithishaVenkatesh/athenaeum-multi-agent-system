/**
 * Manager Insights API client — self-contained so the learner `api.ts` is untouched.
 *
 * Reuses only read-only TYPES from `api.ts` (PersonaSummary, PhaseTelemetry); all
 * endpoints here are the additive `/api/manager/*` surface. The chat stream mirrors
 * the learner SSE protocol so the same `PipelineTrace` renders the manager trace.
 */

import { API_BASE_URL, type PersonaSummary, type PhaseTelemetry } from "@/lib/api";

// ── Insight DTOs (mirror app/manager/schemas.py) ─────────────────────────────

export interface ReadinessBreakdown {
  go: number;
  conditional: number;
  not_yet: number;
  total: number;
}

export interface CohortReadiness {
  label: string;
  go: number;
  conditional: number;
  not_yet: number;
  total: number;
}

export interface CertTargetProgress {
  vertical: string;
  cert: string;
  target_quarter: string;
  member_count: number;
  ready_count: number;
}

export interface PlatformEngagement {
  members_total: number;
  members_active: number;
  assessments_attempted: number;
  assessments_passed: number;
  modules_with_a_pass: number;
  modules_completed: number;
  pass_rate: number | null;
  has_activity: boolean;
}

export type RiskArea = "exam_readiness" | "engagement";
export type RiskSeverity = "high" | "medium" | "low";

export interface RiskFlag {
  area: RiskArea;
  severity: RiskSeverity;
  title: string;
  detail: string;
}

export interface TeamInsights {
  team_id: string;
  team_name: string;
  manager_codename: string;
  member_count: number;
  readiness: ReadinessBreakdown;
  by_seniority: CohortReadiness[];
  cert_targets: CertTargetProgress[];
  engagement: PlatformEngagement;
  risks: RiskFlag[];
  disclaimer: string;
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    throw new Error(`Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

/** Managers only (the front-page "Team lead" entry). */
export async function fetchManagers(signal?: AbortSignal): Promise<PersonaSummary[]> {
  const all = await getJson<PersonaSummary[]>("/api/workiq/personas", signal);
  return all.filter((p) => p.is_manager);
}

export function fetchTeamInsights(
  employeeId: string,
  signal?: AbortSignal,
): Promise<TeamInsights> {
  return getJson<TeamInsights>(`/api/manager/${employeeId}/insights`, signal);
}

// ── Manager chat (SSE, same event protocol as the learner chat) ──────────────

export interface ManagerHistoryTurn {
  role: "user" | "assistant";
  content: string;
}

export interface ManagerStreamHandlers {
  onPhase?: (phase: PhaseTelemetry) => void;
  onToken?: (token: string) => void;
  onBlocked?: (reason: string) => void;
  onError?: (message: string) => void;
  onDone?: () => void;
}

type ManagerEvent =
  | { type: "phase"; phase: PhaseTelemetry }
  | { type: "token"; token: string }
  | { type: "blocked"; reason: string }
  | { type: "error"; message: string }
  | { type: "done" };

function dispatch(event: ManagerEvent, handlers: ManagerStreamHandlers): void {
  switch (event.type) {
    case "phase":
      handlers.onPhase?.(event.phase);
      break;
    case "token":
      handlers.onToken?.(event.token);
      break;
    case "blocked":
      handlers.onBlocked?.(event.reason);
      break;
    case "error":
      handlers.onError?.(event.message);
      break;
    case "done":
      handlers.onDone?.();
      break;
  }
}

/** POST a manager turn and stream the guarded, grounded answer over SSE. */
export async function streamManagerChat(
  employeeId: string,
  content: string,
  history: ManagerHistoryTurn[],
  handlers: ManagerStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/manager/${employeeId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ content, history }),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`Chat request failed (${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.startsWith("data:")) continue;
      const payload = JSON.parse(line.slice(5).trim()) as ManagerEvent;
      dispatch(payload, handlers);
    }
  }
}
