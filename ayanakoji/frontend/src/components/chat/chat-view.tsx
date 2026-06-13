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

import { ArrowDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { ChatComposer } from "@/components/chat/chat-composer";
import { CourseSuggestionCard } from "@/components/chat/course-suggestion-card";
import { MessageBubble } from "@/components/chat/message-bubble";
import { PaceChooser } from "@/components/chat/pace-chooser";
import { PipelineTrace } from "@/components/chat/pipeline-trace";
import { StudyPlanCard } from "@/components/chat/study-plan-card";
import { Button } from "@/components/ui/button";
import { useWorkspace } from "@/components/workspace/workspace-context";
import {
  acceptCourse,
  createCourse,
  getCourse,
  setPace,
  streamMessage,
  type Pace,
  type PaceRequest,
  type PhaseTelemetry,
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
    error: null,
    streaming: true,
  };
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

export function ChatView({ courseId }: { courseId?: string }) {
  const { personaId, reloadCourses } = useWorkspace();
  const [activeCourseId, setActiveCourseId] = useState<string | undefined>(courseId);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [atBottom, setAtBottom] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);

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
        setTurns(
          loaded.messages.map((m): Turn =>
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
                  error: null,
                  streaming: false,
                },
          ),
        );
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

      setTurns((prev) => [...prev, { kind: "user", text }, emptyAssistantTurn()]);

      await streamMessage(id, text, {
        onPhase: (phase) => patchLastAssistant((t) => ({ ...t, phases: [...t.phases, phase] })),
        onToken: (token) => patchLastAssistant((t) => ({ ...t, text: t.text + token })),
        onSuggestion: (suggestion) => patchLastAssistant((t) => ({ ...t, suggestion })),
        onPlan: (plan) => patchLastAssistant((t) => ({ ...t, plan })),
        onPaceRequest: (paceRequest) => patchLastAssistant((t) => ({ ...t, paceRequest })),
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

  const isEmpty = turns.length === 0;

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
                    Build my study plan
                  </Button>
                )}
                {turn.paceRequest && (
                  <PaceChooser
                    request={turn.paceRequest}
                    chosen={turn.paceChosen}
                    busy={busy || turn.paceChosen !== null}
                    onChoose={(pace) => handlePace(index, pace)}
                  />
                )}
                {turn.plan && <StudyPlanCard plan={turn.plan} courseId={activeCourseId} />}
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
        <ChatComposer onSend={handleSend} busy={busy} />
        <p className="text-muted-foreground/70 mt-2 text-center text-xs">
          Answers are grounded and AI-generated. Reasoning is shown for every turn.
        </p>
      </div>
    </div>
  );
}
