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

import { ArrowLeft, CheckCircle2, Loader2, Send, XCircle } from "lucide-react";
import Link from "next/link";
import { use, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  getAssessmentSession,
  listModuleAssessments,
  sendLlmTurn,
  startAssessment,
  startLlmQuestion,
  submitLlm,
  type AssessmentSession,
  type LlmSubmitResult,
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

  const [phase, setPhase] = useState<Phase>("loading");
  const [session, setSession] = useState<AssessmentSession | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamingReply, setStreamingReply] = useState("");
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<LlmSubmitResult | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const moduleHref = `/chat/${courseId}/modules/${moduleId}`;
  const choicesHref = `/chat/${courseId}/modules/${moduleId}/assessment/choices`;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingReply]);

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

        // Already passed LLM → show "already complete" briefly then back.
        if (llmSummaries.some((a) => a.passed === true)) {
          if (!cancelled) {
            setPhase("redirect");
            router.replace(moduleHref);
          }
          return;
        }

        // Resume in-progress LLM session.
        const inProgress = llmSummaries.find((a) => a.completed_at === null);
        let s: AssessmentSession;
        if (inProgress) {
          s = await getAssessmentSession(courseId, inProgress.id);
        } else {
          s = await startAssessment(courseId, moduleId, "llm");
        }
        if (cancelled) return;
        setSession(s);

        // Load/obtain the grader opening message.
        const q = await startLlmQuestion(courseId, s.id);
        if (cancelled) return;

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
  }, [courseId, moduleId, choicesHref, moduleHref, router]);

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
            <Button onClick={() => router.push(moduleHref)}>
              Back to Module
            </Button>
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

      <div className="border-border mt-4 flex gap-2 border-t pt-4">
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type your answer…"
          rows={3}
          className="resize-none"
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
