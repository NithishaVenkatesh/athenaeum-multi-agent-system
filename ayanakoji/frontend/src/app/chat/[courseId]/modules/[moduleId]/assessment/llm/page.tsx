"use client";

/**
 * LLM (oral) assessment page.
 *
 * Flow:
 *  1. Load or start the LLM assessment session.
 *  2. Show the grader's opening message (startLlmQuestion).
 *  3. Accept learner replies; send each to sendLlmTurn (SSE).
 *  4. When the grader calls grade_answer, the stream emits a "grade" event.
 *  5. Auto-submit once the question is graded. Show results + pass/fail.
 */

import { ArrowLeft, ArrowRight, CheckCircle2, Loader2, Send, Trophy, XCircle } from "lucide-react";
import Link from "next/link";
import { use, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  ApiError,
  getAssessmentSession,
  listModuleAssessments,
  listModules,
  sendLlmTurn,
  startAssessment,
  startLlmQuestion,
  submitLlm,
  type AssessmentSession,
  type CourseModuleProgress,
  type LlmSubmitResult,
  type SessionLlmQuestion,
} from "@/lib/api";

type Phase = "loading" | "chat" | "grading" | "results" | "redirect" | "error";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export default function LlmAssessmentPage({
  params,
}: {
  params: Promise<{ courseId: string; moduleId: string }>;
}) {
  const { courseId, moduleId } = use(params);
  const router = useRouter();
  const isRetake = useSearchParams().get("retake") === "1";

  const [phase, setPhase] = useState<Phase>("loading");
  const [session, setSession] = useState<AssessmentSession | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamingReply, setStreamingReply] = useState("");
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<LlmSubmitResult | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  // The course's ordered modules — used on a pass to point at the *next* module
  // (or "Complete Course" when this is the last one) instead of looping back here.
  const [modules, setModules] = useState<CourseModuleProgress[] | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const moduleHref = `/chat/${courseId}/modules/${moduleId}`;
  const choicesHref = `/chat/${courseId}/modules/${moduleId}/assessment/choices`;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingReply]);

  // Load the module list once so the results screen can resolve "what's next".
  // Failure leaves `modules` null → the results screen falls back to "Back to Module".
  useEffect(() => {
    let cancelled = false;
    listModules(courseId)
      .then((m) => !cancelled && setModules(m))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [courseId]);

  useEffect(() => {
    let cancelled = false;
    async function init() {
      try {
        const summaries = await listModuleAssessments(courseId, moduleId);
        const llmSummaries = summaries.filter((a) => a.type === "llm");
        const choicesSummaries = summaries.filter((a) => a.type === "choices");

        // Choices not yet passed → redirect back.
        if (!choicesSummaries.some((a) => a.passed === true)) {
          if (!cancelled) {
            setPhase("redirect");
            router.replace(choicesHref);
          }
          return;
        }

        let s: AssessmentSession;
        if (isRetake) {
          // Retake from the Evaluations tab: force a fresh oral attempt (choices
          // stay a precondition, checked above), bypassing the passed-redirect.
          s = await startAssessment(courseId, moduleId, "llm", true);
        } else {
          // Already passed LLM → show "already complete" briefly then back.
          if (llmSummaries.some((a) => a.passed === true)) {
            if (!cancelled) {
              setPhase("redirect");
              router.replace(moduleHref);
            }
            return;
          }
          // Resume in-progress LLM session, else start a new one. A stale
          // in-progress id (deleted between the list and this fetch) 404s here;
          // recover by starting fresh rather than erroring.
          const inProgress = llmSummaries.find((a) => a.completed_at === null);
          if (inProgress) {
            try {
              s = await getAssessmentSession(courseId, inProgress.id);
            } catch (err: unknown) {
              if (!(err instanceof ApiError) || err.status !== 404) throw err;
              s = await startAssessment(courseId, moduleId, "llm", true);
            }
          } else {
            s = await startAssessment(courseId, moduleId, "llm");
          }
        }
        if (cancelled) return;

        // Open the grader's first message. A 404 here means the attempt id we
        // hold went stale — the backend's latest-only model deletes the prior
        // attempt whenever a new one starts (a dev StrictMode double-mount, a
        // back/forward re-entry, or a server restart can all replace it). That
        // is recoverable, not terminal: mint a fresh attempt and retry once
        // rather than dead-ending the learner on an error screen.
        let q: SessionLlmQuestion;
        try {
          q = await startLlmQuestion(courseId, s.id);
        } catch (err: unknown) {
          if (!(err instanceof ApiError) || err.status !== 404) throw err;
          s = await startAssessment(courseId, moduleId, "llm", true);
          q = await startLlmQuestion(courseId, s.id);
        }
        if (cancelled) return;
        setSession(s);

        const opening = q.messages[0];
        if (opening) {
          setMessages([{ role: opening.role as "assistant", content: opening.content }]);
        }
        setPhase("chat");
      } catch (err: unknown) {
        if (!cancelled) {
          const msg = err instanceof Error ? err.message : "Failed to load assessment.";
          setErrorMsg(msg);
          setPhase("error");
        }
      }
    }
    init();
    return () => {
      cancelled = true;
    };
  }, [courseId, moduleId, choicesHref, moduleHref, router, isRetake]);

  async function handleSend() {
    if (!session || !input.trim() || sending) return;
    const q = session.llm_questions[0];
    if (!q) return;

    const userMsg: ChatMessage = { role: "user", content: input.trim() };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setSending(true);
    setStreamingReply("");

    let graded = false;
    let accum = "";

    try {
      await sendLlmTurn(courseId, session.id, q.id, userMsg.content, {
        onToken: (token) => {
          accum += token;
          setStreamingReply(accum);
        },
        onGrade: async (score, reasoning) => {
          graded = true;
          setStreamingReply("");
          setPhase("grading");
          // Auto-submit after grade received.
          try {
            const r = await submitLlm(courseId, session.id);
            setResult(r);
            setPhase("results");
          } catch {
            // If submit fails show the score inline.
            setResult({
              assessment_id: session.id,
              score,
              passed: score >= 5,
              questions: [
                {
                  id: q.id,
                  prompt: q.prompt,
                  score,
                  reasoning,
                  turn_count: q.turn_count + 1,
                  grading_complete: true,
                  messages: [],
                },
              ],
            });
            setPhase("results");
          }
        },
        onError: (msg) => {
          setErrorMsg(msg);
          setPhase("error");
        },
        onDone: () => {
          if (!graded && accum) {
            setMessages((prev) => [
              ...prev,
              { role: "assistant", content: accum },
            ]);
            setStreamingReply("");
          }
        },
      });
    } catch {
      if (!graded) {
        setErrorMsg("Connection lost. Please try again.");
        setPhase("error");
      }
    } finally {
      setSending(false);
    }
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  if (phase === "loading" || phase === "redirect") {
    return (
      <div className="text-muted-foreground flex min-h-screen items-center justify-center gap-2 text-sm">
        <Loader2 className="size-4 animate-spin" />
        {phase === "redirect" ? "Redirecting…" : "Loading assessment…"}
      </div>
    );
  }

  if (phase === "grading") {
    return (
      <div className="text-muted-foreground flex min-h-screen items-center justify-center gap-2 text-sm">
        <Loader2 className="size-4 animate-spin" /> Evaluating your answer…
      </div>
    );
  }

  if (phase === "error") {
    return (
      <div className="mx-auto max-w-xl px-4 py-16 text-center">
        <p className="text-destructive text-sm">{errorMsg}</p>
        <Link href={moduleHref} className="text-brand mt-4 inline-block text-sm">
          Back to module
        </Link>
      </div>
    );
  }

  if (phase === "results" && result) {
    const passed = result.passed;
    const q = result.questions[0];
    // Resolve this module's position so a pass advances the learner: the next
    // module if there is one, otherwise the whole course is done.
    const moduleIndex = modules?.findIndex((m) => m.module_id === moduleId) ?? -1;
    const nextModule =
      modules && moduleIndex >= 0 ? (modules[moduleIndex + 1] ?? null) : null;
    const isLastModule = modules !== null && moduleIndex >= 0 && nextModule === null;
    return (
      <div className="mx-auto max-w-xl px-4 py-8">
        <h1 className="font-display text-xl font-semibold">Oral Assessment</h1>
        <div className="mt-2 flex items-center gap-2">
          {passed ? (
            <span className="text-brand flex items-center gap-1.5 text-sm font-medium">
              <CheckCircle2 className="size-4" /> Passed — {q?.score ?? "—"}/10
            </span>
          ) : (
            <span className="text-destructive flex items-center gap-1.5 text-sm font-medium">
              <XCircle className="size-4" /> Failed — {q?.score ?? "—"}/10
            </span>
          )}
        </div>

        {q?.reasoning && (
          <div className="border-border mt-4 rounded-xl border p-4 text-sm">
            <p className="text-muted-foreground mb-1 text-xs font-medium uppercase tracking-wide">
              Examiner feedback
            </p>
            <p>{q.reasoning}</p>
          </div>
        )}

        <div className="mt-8 flex gap-3">
          {passed ? (
            modules === null ? (
              <Button disabled className="gap-1.5">
                <Loader2 className="size-4 animate-spin" /> Loading…
              </Button>
            ) : nextModule ? (
              <Button
                className="gap-1.5"
                onClick={() =>
                  router.push(`/chat/${courseId}/modules/${nextModule.module_id}`)
                }
              >
                Next Module <ArrowRight className="size-4" />
              </Button>
            ) : isLastModule ? (
              <Button
                className="gap-1.5"
                onClick={() => router.push(`/chat/${courseId}?completed=1`)}
              >
                <Trophy className="size-4" /> Complete Course
              </Button>
            ) : (
              // Module position couldn't be resolved — neutral fallback.
              <Button onClick={() => router.push(moduleHref)}>Back to Module</Button>
            )
          ) : (
            <>
              <Button variant="outline" onClick={() => router.push(moduleHref)}>
                Return to Module
              </Button>
              <Button
                onClick={() =>
                  router.push(
                    `/chat/${courseId}?feedback=llm&module=${moduleId}`,
                  )
                }
              >
                Get Feedback
              </Button>
            </>
          )}
        </div>
      </div>
    );
  }

  // Chat phase.
  const q = session?.llm_questions[0];
  return (
    <div className="mx-auto flex max-w-xl flex-col px-4 py-6" style={{ minHeight: "80vh" }}>
      <div className="mb-4 flex items-center gap-2">
        <Link
          href={moduleHref}
          className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-sm"
        >
          <ArrowLeft className="size-4" /> Back
        </Link>
        <span className="text-muted-foreground text-sm">Oral Assessment</span>
        {q && (
          <span className="text-muted-foreground ml-auto text-xs">
            Turn {q.turn_count + messages.filter((m) => m.role === "user").length} of up to 8
          </span>
        )}
      </div>

      <div className="flex flex-1 flex-col gap-3 overflow-y-auto">
        {messages.map((m, i) => (
          <div
            key={i}
            className={`rounded-xl px-4 py-3 text-sm ${
              m.role === "assistant"
                ? "bg-muted text-foreground self-start max-w-[85%]"
                : "bg-brand text-white self-end max-w-[85%]"
            }`}
          >
            {m.content}
          </div>
        ))}
        {streamingReply && (
          <div className="bg-muted text-foreground self-start max-w-[85%] rounded-xl px-4 py-3 text-sm">
            {streamingReply}
            <span className="ml-1 inline-block animate-pulse">▋</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Bordered composer (matches ChatComposer): a clearly visible surface so the
          field reads as an input even when unfocused, with a focus-within ring. */}
      <div className="border-border bg-card focus-within:border-brand/50 focus-within:ring-brand/15 mt-4 flex items-end gap-2 rounded-2xl border p-2 shadow-sm transition-shadow focus-within:ring-[3px]">
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type your answer…"
          rows={3}
          // `field-sizing-content` (base Textarea) auto-grows; `overflow-y-auto` is what
          // makes it honour `max-h` and scroll past the cap instead of growing unbounded.
          className="max-h-75 min-h-16 resize-none overflow-y-auto border-0 bg-transparent px-2 py-1.5 shadow-none focus-visible:ring-0 disabled:opacity-60 dark:bg-transparent"
          disabled={sending}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSend();
          }}
        />
        <Button
          onClick={handleSend}
          disabled={sending || !input.trim()}
          size="icon"
          className="self-end"
        >
          {sending ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
        </Button>
      </div>
    </div>
  );
}
