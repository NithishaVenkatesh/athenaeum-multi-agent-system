"use client";

/**
 * The chat surface — and a chat IS a course. A new chat (no courseId) has its
 * first message create the course; an existing one loads from the backend.
 *
 * Each turn is streamed as the full agent pipeline: per-phase telemetry (shown
 * in an inspectable trace), answer tokens, an optional course suggestion, and
 * explicit blocked/error events surfaced as toasts. The backend persists the
 * transcript; the live trace and suggestion live in this component's state.
 */

import { ArrowDown, ArrowRight, MessageSquarePlus } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { ChatComposer } from "@/components/chat/chat-composer";
import { CourseSuggestionCard } from "@/components/chat/course-suggestion-card";
import { MessageBubble } from "@/components/chat/message-bubble";
import { PaceChooser } from "@/components/chat/pace-chooser";
import { PipelineTrace } from "@/components/chat/pipeline-trace";
import { SkillAssessmentCard } from "@/components/chat/skill-assessment-card";
import { SkillGateCard } from "@/components/chat/skill-gate-card";
import { SkillResultCard } from "@/components/chat/skill-result-card";
import { StudyPlanCard } from "@/components/chat/study-plan-card";
import { TypingIndicator } from "@/components/chat/typing-indicator";
import { Button } from "@/components/ui/button";
import { useWorkspace } from "@/components/workspace/workspace-context";
import {
  acceptCourse,
  approvePlan,
  createCourse,
  getCourse,
  gradeSkillCheck,
  listModules,
  setDeadline,
  setPace,
  skillFresher,
  startSkillCheck,
  streamFeedback,
  streamMessage,
  type AssessmentType,
  type NewChat,
  type Pace,
  type PaceRequest,
  type PhaseTelemetry,
  type SkillAnswer,
  type SkillCheck,
  type SkillGateRequest,
  type SkillResult,
  type StudyPlan,
  type Suggestion,
} from "@/lib/api";

type AcceptState = "idle" | "accepting" | "accepted" | "declined";

interface UserTurn {
  kind: "user";
  text: string;
}

interface AssistantTurn {
  kind: "assistant";
  phases: PhaseTelemetry[];
  text: string;
  suggestion: Suggestion | null;
  suggestionState: AcceptState;
  chosenId: string | null;
  plan: StudyPlan | null;
  paceRequest: PaceRequest | null;
  paceChosen: Pace | null;
  skillGate: SkillGateRequest | null;
  skillCheck: SkillCheck | null; // ephemeral: the active quiz (not persisted)
  skillBusy: boolean;
  skillResult: SkillResult | null;
  deadlineDone: boolean;
  approveState: "idle" | "approving" | "approved";
  newChat: NewChat | null;
  error: string | null;
  streaming: boolean;
}

type Turn = UserTurn | AssistantTurn;

function emptyAssistantTurn(): AssistantTurn {
  return {
    kind: "assistant",
    phases: [],
    text: "",
    suggestion: null,
    suggestionState: "idle",
    chosenId: null,
    plan: null,
    paceRequest: null,
    paceChosen: null,
    skillGate: null,
    skillCheck: null,
    skillBusy: false,
    skillResult: null,
    deadlineDone: false,
    approveState: "idle",
    newChat: null,
    error: null,
    streaming: true,
  };
}

/**
 * A streaming turn that has not yet surfaced any visible reply — no answer text
 * and none of the interactive cards. While true, show the thinking indicator.
 */
function isAwaitingReply(turn: AssistantTurn): boolean {
  return (
    turn.streaming &&
    !turn.text &&
    !turn.suggestion &&
    !turn.plan &&
    !turn.paceRequest &&
    !turn.skillGate &&
    !turn.skillCheck &&
    !turn.skillResult &&
    !turn.newChat
  );
}

function updateAssistant(
  turns: Turn[],
  index: number,
  patch: (turn: AssistantTurn) => AssistantTurn,
): Turn[] {
  const next = [...turns];
  const turn = next[index];
  if (turn && turn.kind === "assistant") next[index] = patch(turn);
  return next;
}

/**
 * One course per chat. Two shapes:
 * - locked chat → button starts a fresh chat to explore another course;
 * - course already registered elsewhere → button opens that existing chat.
 */
function NewChatNotice({ newChat }: { newChat: NewChat }) {
  const target = newChat.target_course_id;
  const href = target ? `/chat/${target}` : "/chat";
  const label = target
    ? `Open ${newChat.target_title ?? "that chat"}`
    : "Start a new chat";
  return (
    <div className="border-brand/30 bg-brand/5 flex items-center justify-between gap-3 rounded-2xl border px-4 py-3">
      <p className="text-muted-foreground text-xs text-pretty">{newChat.prompt}</p>
      <Link
        href={href}
        className="border-input bg-background hover:bg-accent hover:text-accent-foreground inline-flex shrink-0 items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors"
      >
        {target ? (
          <ArrowRight className="size-3.5" />
        ) : (
          <MessageSquarePlus className="size-3.5" />
        )}{" "}
        {label}
      </Link>
    </div>
  );
}

export function ChatView({
  courseId,
  feedback,
}: {
  courseId?: string;
  /** Set when arriving from the "Get Feedback" button — streams grounded feedback. */
  feedback?: { kind: AssessmentType; moduleId: string };
}) {
  const { personaId, reloadCourses } = useWorkspace();
  const [activeCourseId, setActiveCourseId] = useState<string | undefined>(courseId);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [atBottom, setAtBottom] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const autoSentRef = useRef(false);

  // Show a "scroll to bottom" button whenever the latest turn is out of view.
  useEffect(() => {
    const target = bottomRef.current;
    if (!target || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      ([entry]) => setAtBottom(entry.isIntersecting),
      { rootMargin: "0px 0px -80px 0px" },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, []);

  function scrollToBottom() {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }

  // Load an existing course's persisted conversation (text only; no live trace).
  useEffect(() => {
    if (!courseId) return;
    let active = true;
    getCourse(courseId)
      .then((loaded) => {
        if (!active) return;
        setActiveCourseId(loaded.id);
        const enrolled = loaded.catalog_id;
        // Once the skill step is resolved (a skill_result message exists) the gate
        // is not re-offered on reload — it lives on an earlier turn than the result.
        const skillResolved = loaded.messages.some((m) => m.meta?.skill_result);
        // An in-progress skill check is course-level; restore it onto the latest
        // turn that offered the gate so the open quiz card survives a chat switch.
        const activeCheck = skillResolved ? null : (loaded.skill_check_active ?? null);
        let lastGateIndex = -1;
        loaded.messages.forEach((m, i) => {
          if (m.role === "assistant" && m.meta?.skill_gate) lastGateIndex = i;
        });
        setTurns(
          loaded.messages.map((m, index): Turn =>
            m.role === "user"
              ? { kind: "user", text: m.content }
              : {
                  kind: "assistant",
                  phases: m.meta?.phases ?? [],
                  text: m.content,
                  suggestion: m.meta?.suggestion ?? null,
                  // If the course is already linked, a restored suggestion reads as accepted.
                  suggestionState: enrolled && m.meta?.suggestion ? "accepted" : "idle",
                  chosenId: enrolled ?? null,
                  plan: m.meta?.plan ?? null,
                  paceRequest: m.meta?.pace_request ?? null,
                  paceChosen: null,
                  skillGate: skillResolved ? null : (m.meta?.skill_gate ?? null),
                  skillCheck: index === lastGateIndex ? activeCheck : null,
                  skillBusy: false,
                  skillResult: m.meta?.skill_result ?? null,
                  deadlineDone: false,
                  approveState: "idle",
                  newChat: m.meta?.new_chat ?? null,
                  error: null,
                  streaming: false,
                },
          ),
        );
        // If the plan was approved, persisted modules exist — mark the latest
        // plan turn approved so the card shows the Modules link, not Approve.
        listModules(loaded.id)
          .then((mods) => {
            if (!active || mods.length === 0) return;
            setTurns((prev) => {
              const next = [...prev];
              for (let i = next.length - 1; i >= 0; i -= 1) {
                const t = next[i];
                if (t.kind === "assistant" && t.plan) {
                  next[i] = { ...t, approveState: "approved" };
                  break;
                }
              }
              return next;
            });
          })
          .catch(() => {});
      })
      .catch(() => active && setLoadError("Could not load this chat."));
    return () => {
      active = false;
    };
  }, [courseId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  // Patch the trailing assistant turn immutably.
  function patchLastAssistant(patch: (turn: AssistantTurn) => AssistantTurn) {
    setTurns((prev) => {
      const next = [...prev];
      for (let i = next.length - 1; i >= 0; i -= 1) {
        const turn = next[i];
        if (turn.kind === "assistant") {
          next[i] = patch(turn);
          break;
        }
      }
      return next;
    });
  }

  async function handleSend(text: string) {
    setBusy(true);
    // Render the learner's turn + a streaming placeholder immediately, before any
    // network call. For a brand-new chat this used to wait on the createCourse
    // round-trip, leaving the screen blank from Enter until the reply began.
    setTurns((prev) => [...prev, { kind: "user", text }, emptyAssistantTurn()]);
    let id = activeCourseId;
    try {
      if (!id) {
        const created = await createCourse(personaId, text);
        id = created.id;
        setActiveCourseId(created.id);
        // Reflect the new course in the URL without a remount so the stream below
        // keeps running on this mounted component.
        window.history.replaceState(null, "", `/chat/${created.id}`);
        void reloadCourses();
      }

      await streamMessage(id, text, {
        onPhase: (phase) => patchLastAssistant((t) => ({ ...t, phases: [...t.phases, phase] })),
        onToken: (token) => patchLastAssistant((t) => ({ ...t, text: t.text + token })),
        onSuggestion: (suggestion) => patchLastAssistant((t) => ({ ...t, suggestion })),
        onPlan: (plan) => patchLastAssistant((t) => ({ ...t, plan })),
        onPaceRequest: (paceRequest) => patchLastAssistant((t) => ({ ...t, paceRequest })),
        onSkillGate: (skillGate) => patchLastAssistant((t) => ({ ...t, skillGate })),
        onNewChat: (newChat) => patchLastAssistant((t) => ({ ...t, newChat })),
        onBlocked: (reason) => {
          toast.error("Message blocked", { description: reason });
          patchLastAssistant((t) => ({ ...t, text: reason }));
        },
        onError: (message) => {
          toast.error("Something went wrong", { description: message });
          patchLastAssistant((t) => ({ ...t, error: message, text: t.text || message }));
        },
      });

      patchLastAssistant((t) => ({ ...t, streaming: false }));
      void reloadCourses();
    } catch {
      toast.error("Connection lost", { description: "Could not reach the assistant. Try again." });
      patchLastAssistant((t) => ({
        ...t,
        streaming: false,
        error: "Could not reach the assistant.",
        text: t.text || "Could not reach the assistant. Please try again.",
      }));
    } finally {
      setBusy(false);
    }
  }

  // Stream grounded feedback on the learner's latest attempt into the chat. Unlike
  // handleSend this skips the topic gate (the backend grounds on the module + the
  // learner's answers), so it answers with real feedback instead of a refusal.
  async function handleFeedback(kind: AssessmentType, moduleId: string) {
    if (!activeCourseId) return;
    const label = kind === "choices" ? "quiz" : "oral exam";
    setBusy(true);
    setTurns((prev) => [
      ...prev,
      { kind: "user", text: `Can you give me feedback on my ${label}?` },
      emptyAssistantTurn(),
    ]);
    try {
      await streamFeedback(activeCourseId, moduleId, kind, {
        onPhase: (phase) => patchLastAssistant((t) => ({ ...t, phases: [...t.phases, phase] })),
        onToken: (token) => patchLastAssistant((t) => ({ ...t, text: t.text + token })),
        onError: (message) => {
          toast.error("Something went wrong", { description: message });
          patchLastAssistant((t) => ({ ...t, error: message, text: t.text || message }));
        },
      });
      patchLastAssistant((t) => ({ ...t, streaming: false }));
      void reloadCourses();
    } catch {
      toast.error("Connection lost", { description: "Could not load feedback. Try again." });
      patchLastAssistant((t) => ({
        ...t,
        streaming: false,
        error: "Could not load feedback.",
        text: t.text || "Could not load feedback. Please try again.",
      }));
    } finally {
      setBusy(false);
    }
  }

  function handleAccept(turnIndex: number, catalogId: string) {
    if (!activeCourseId) return;
    const turn = turns[turnIndex];
    const option =
      turn?.kind === "assistant"
        ? turn.suggestion?.options.find((o) => o.catalog_id === catalogId)
        : undefined;
    setTurns((prev) =>
      updateAssistant(prev, turnIndex, (t) => ({
        ...t,
        suggestionState: "accepting",
        chosenId: catalogId,
      })),
    );
    acceptCourse(activeCourseId, catalogId)
      .then(() => {
        setTurns((prev) =>
          updateAssistant(prev, turnIndex, (t) => ({ ...t, suggestionState: "accepted" })),
        );
        toast.success("Enrolled", {
          description: `${option?.title ?? "Course"} — attempt 1 started.`,
        });
        void reloadCourses();
      })
      .catch(() => {
        setTurns((prev) =>
          updateAssistant(prev, turnIndex, (t) => ({
            ...t,
            suggestionState: "idle",
            chosenId: null,
          })),
        );
        toast.error("Could not enroll", { description: "Please try again." });
      });
  }

  function handleDecline(turnIndex: number) {
    setTurns((prev) =>
      updateAssistant(prev, turnIndex, (t) => ({ ...t, suggestionState: "declined" })),
    );
  }

  async function handlePace(turnIndex: number, pace: Pace) {
    if (!activeCourseId) return;
    setTurns((prev) => updateAssistant(prev, turnIndex, (t) => ({ ...t, paceChosen: pace })));
    try {
      await setPace(activeCourseId, pace);
      await handleSend("Build me a study plan for this course");
    } catch {
      setTurns((prev) => updateAssistant(prev, turnIndex, (t) => ({ ...t, paceChosen: null })));
      toast.error("Could not set pace", { description: "Please try again." });
    }
  }

  function patchTurnAt(index: number, patch: (t: AssistantTurn) => AssistantTurn) {
    setTurns((prev) => updateAssistant(prev, index, patch));
  }

  async function handleTakeSkillCheck(index: number) {
    if (!activeCourseId) return;
    patchTurnAt(index, (t) => ({ ...t, skillBusy: true }));
    try {
      const check = await startSkillCheck(activeCourseId);
      patchTurnAt(index, (t) => ({ ...t, skillCheck: check, skillBusy: false }));
    } catch {
      patchTurnAt(index, (t) => ({ ...t, skillBusy: false }));
      toast.error("Could not start the skill check", { description: "Please try again." });
    }
  }

  async function handleFresher(index: number) {
    if (!activeCourseId) return;
    patchTurnAt(index, (t) => ({ ...t, skillBusy: true }));
    try {
      const result = await skillFresher(activeCourseId);
      patchTurnAt(index, (t) => ({ ...t, skillResult: result, skillGate: null, skillBusy: false }));
    } catch {
      patchTurnAt(index, (t) => ({ ...t, skillBusy: false }));
      toast.error("Could not continue", { description: "Please try again." });
    }
  }

  async function handleSubmitSkill(index: number, answers: SkillAnswer[]) {
    if (!activeCourseId) return;
    patchTurnAt(index, (t) => ({ ...t, skillBusy: true }));
    try {
      const result = await gradeSkillCheck(activeCourseId, answers);
      patchTurnAt(index, (t) => ({ ...t, skillResult: result, skillCheck: null, skillBusy: false }));
    } catch {
      patchTurnAt(index, (t) => ({ ...t, skillBusy: false }));
      toast.error("Could not grade the skill check", { description: "Please try again." });
    }
  }

  async function handleDeadlineContinue(index: number, deadline: string | null) {
    if (!activeCourseId) return;
    patchTurnAt(index, (t) => ({ ...t, deadlineDone: true }));
    try {
      await setDeadline(activeCourseId, deadline);
      await handleSend("Build me a study plan for this course");
    } catch {
      patchTurnAt(index, (t) => ({ ...t, deadlineDone: false }));
      toast.error("Could not save the deadline", { description: "Please try again." });
    }
  }

  async function handleApprove(index: number) {
    if (!activeCourseId) return;
    patchTurnAt(index, (t) => ({ ...t, approveState: "approving" }));
    try {
      await approvePlan(activeCourseId);
      patchTurnAt(index, (t) => ({ ...t, approveState: "approved" }));
      toast.success("Scheduled", { description: "Your modules now have deadlines." });
      void reloadCourses();
    } catch {
      patchTurnAt(index, (t) => ({ ...t, approveState: "idle" }));
      toast.error("Could not schedule the plan", { description: "Please try again." });
    }
  }

  // Auto-request feedback once the course finishes loading (from the Get Feedback
  // button). This streams from the dedicated grounded endpoint, not the chat pipeline.
  // The kickoff is deferred a tick so the stream's state updates land after this
  // effect, not synchronously inside it.
  useEffect(() => {
    if (!feedback || autoSentRef.current || busy) return;
    if (courseId && turns.length === 0) return; // still loading existing turns
    autoSentRef.current = true;
    const { kind, moduleId } = feedback;
    const id = setTimeout(() => void handleFeedback(kind, moduleId), 0);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [feedback?.kind, feedback?.moduleId, turns.length, busy]);

  const isEmpty = turns.length === 0;
  // HITL gate: while the last turn is asking for a pace, or a quiz is open, typing
  // is disabled so the learner uses the controls (the backend also 409s on a
  // pending pace). The skill gate and the plan preview do NOT lock: a learner may
  // type at the gate, and the preview accepts free-text corrections that re-plan.
  const lastTurn = turns[turns.length - 1];
  const lastAssistant = lastTurn?.kind === "assistant" ? lastTurn : null;
  const paceLocked = Boolean(lastAssistant?.paceRequest) && lastAssistant?.paceChosen == null;
  const quizLocked = Boolean(lastAssistant?.skillCheck);
  const inputLocked = paceLocked || quizLocked;

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-4">
      <div className="flex-1 space-y-4 py-4">
        {loadError ? (
          <p role="alert" className="text-destructive text-sm">
            {loadError}
          </p>
        ) : isEmpty ? (
          <div className="flex h-full flex-col items-center justify-center pt-24 text-center">
            <h2 className="font-display text-3xl tracking-tight">What would you like to learn?</h2>
            <p className="text-muted-foreground mt-2 max-w-sm text-sm text-pretty">
              Ask about any Azure topic to begin. I&apos;ll ground answers in approved course
              content, show my reasoning, and help you commit to a path.
            </p>
          </div>
        ) : (
          turns.map((turn, index) =>
            turn.kind === "user" ? (
              <MessageBubble key={index} role="user" content={turn.text} />
            ) : (
              <div key={index} className="space-y-2">
                {turn.phases.length > 0 && (
                  <PipelineTrace phases={turn.phases} defaultOpen={turn.streaming} />
                )}
                {turn.text && (
                  <MessageBubble role="assistant" content={turn.text} streaming={turn.streaming} />
                )}
                {isAwaitingReply(turn) && <TypingIndicator />}
                {turn.suggestion && (
                  <CourseSuggestionCard
                    suggestion={turn.suggestion}
                    state={turn.suggestionState}
                    chosenId={turn.chosenId}
                    onAccept={(catalogId) => handleAccept(index, catalogId)}
                    onDecline={() => handleDecline(index)}
                  />
                )}
                {turn.suggestionState === "accepted" && (
                  <Button
                    size="sm"
                    variant="outline"
                    className="text-xs"
                    onClick={() => handleSend("Build me a study plan for this course")}
                  >
                    Analyze skill
                  </Button>
                )}
                {turn.skillGate && !turn.skillCheck && !turn.skillResult && (
                  <SkillGateCard
                    request={turn.skillGate}
                    busy={busy || turn.skillBusy}
                    onFresher={() => handleFresher(index)}
                    onTakeCheck={() => handleTakeSkillCheck(index)}
                  />
                )}
                {turn.skillCheck && !turn.skillResult && (
                  <SkillAssessmentCard
                    check={turn.skillCheck}
                    busy={busy || turn.skillBusy}
                    onSubmit={(answers) => handleSubmitSkill(index, answers)}
                  />
                )}
                {turn.skillResult && (
                  <SkillResultCard
                    result={turn.skillResult}
                    done={turn.deadlineDone}
                    busy={busy}
                    onContinue={(deadline) => handleDeadlineContinue(index, deadline)}
                  />
                )}
                {turn.paceRequest && (
                  <PaceChooser
                    request={turn.paceRequest}
                    chosen={turn.paceChosen}
                    busy={busy || turn.paceChosen !== null}
                    onChoose={(pace) => handlePace(index, pace)}
                  />
                )}
                {turn.plan && (
                  <StudyPlanCard
                    plan={turn.plan}
                    courseId={activeCourseId}
                    approveState={turn.approveState}
                    busy={busy}
                    onApprove={() => handleApprove(index)}
                  />
                )}
                {turn.newChat && <NewChatNotice newChat={turn.newChat} />}
              </div>
            ),
          )
        )}
        <div ref={bottomRef} />
      </div>

      <div className="bg-paper sticky bottom-0 pb-5 pt-2">
        {!atBottom && !isEmpty && (
          <button
            type="button"
            onClick={scrollToBottom}
            aria-label="Scroll to latest"
            className="border-border bg-card text-muted-foreground hover:text-foreground absolute -top-12 left-1/2 z-10 flex size-9 -translate-x-1/2 items-center justify-center rounded-full border shadow-md transition-colors"
          >
            <ArrowDown className="size-4" />
          </button>
        )}
        <ChatComposer onSend={handleSend} busy={busy} locked={inputLocked} />
        <p className="text-muted-foreground/70 mt-2 text-center text-xs">
          Answers are grounded and AI-generated. Reasoning is shown for every turn.
        </p>
      </div>
    </div>
  );
}
