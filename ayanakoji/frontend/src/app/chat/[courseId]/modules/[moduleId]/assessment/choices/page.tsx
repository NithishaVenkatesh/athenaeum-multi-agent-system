"use client";

import { ArrowLeft, CheckCircle2, Loader2, XCircle } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  getAssessmentSession,
  listModuleAssessments,
  selectChoiceAnswer,
  startAssessment,
  submitChoices,
  type AssessmentSession,
  type ChoiceSubmitResult,
  type SessionChoiceQuestion,
} from "@/lib/api";

// ── Types ─────────────────────────────────────────────────────────────────────

type Phase = "loading" | "quiz" | "results" | "redirect" | "error";

// ── Choice option button ───────────────────────────────────────────────────────

function ChoiceOption({
  label,
  selected,
  disabled,
  correct,
  wrong,
  onClick,
}: {
  label: string;
  selected: boolean;
  disabled: boolean;
  correct?: boolean;
  wrong?: boolean;
  onClick: () => void;
}) {
  let cls =
    "w-full rounded-lg border px-4 py-3 text-left text-sm transition-colors ";
  if (correct) cls += "border-green-500 bg-green-50 text-green-800 ";
  else if (wrong && selected) cls += "border-red-500 bg-red-50 text-red-700 ";
  else if (selected) cls += "border-brand bg-brand/5 text-foreground ";
  else cls += "border-border hover:border-muted-foreground text-foreground ";
  return (
    <button className={cls} onClick={onClick} disabled={disabled}>
      {label}
    </button>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ChoicesAssessmentPage({
  params,
}: {
  params: Promise<{ courseId: string; moduleId: string }>;
}) {
  const { courseId, moduleId } = use(params);
  const router = useRouter();

  const [phase, setPhase] = useState<Phase>("loading");
  const [session, setSession] = useState<AssessmentSession | null>(null);
  const [qIndex, setQIndex] = useState(0);
  const [selections, setSelections] = useState<Record<string, string[]>>({});
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<ChoiceSubmitResult | null>(null);
  const [errorMsg, setErrorMsg] = useState("");

  const moduleHref = `/chat/${courseId}/modules/${moduleId}`;
  const llmHref = `/chat/${courseId}/modules/${moduleId}/assessment/llm`;

  // Load or start assessment.
  useEffect(() => {
    let cancelled = false;
    async function init() {
      try {
        const summaries = await listModuleAssessments(courseId, moduleId);
        const choicesSummaries = summaries.filter((a) => a.type === "choices");

        // Already passed choices → go straight to LLM gate.
        if (choicesSummaries.some((a) => a.passed === true)) {
          if (!cancelled) {
            setPhase("redirect");
            router.replace(llmHref);
          }
          return;
        }

        // In-progress session (completed_at null) → resume it.
        const inProgress = choicesSummaries.find((a) => a.completed_at === null);
        if (inProgress) {
          const s = await getAssessmentSession(courseId, inProgress.id);
          if (!cancelled) {
            setSession(s);
            setPhase("quiz");
          }
          return;
        }

        // No in-progress session → start a new one.
        const s = await startAssessment(courseId, moduleId, "choices");
        if (!cancelled) {
          setSession(s);
          setPhase("quiz");
        }
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
  }, [courseId, moduleId, llmHref, router]);

  const questions = session?.choice_questions ?? [];
  const q: SessionChoiceQuestion | undefined = questions[qIndex];
  const isLast = qIndex === questions.length - 1;

  function toggleSelection(choice: string) {
    if (!q) return;
    const prev = selections[q.id] ?? [];
    const isMcq = q.kind === "mcq";
    let next: string[];
    if (isMcq) {
      next = prev.includes(choice) ? [] : [choice];
    } else {
      next = prev.includes(choice)
        ? prev.filter((c) => c !== choice)
        : [...prev, choice];
    }
    setSelections((s) => ({ ...s, [q.id]: next }));
    if (session) {
      selectChoiceAnswer(courseId, session.id, q.id, next).catch(() => {});
    }
  }

  async function handleNext() {
    if (isLast) {
      await handleSubmit();
    } else {
      setQIndex((i) => i + 1);
    }
  }

  async function handleSubmit() {
    if (!session) return;
    setSubmitting(true);
    try {
      const r = await submitChoices(courseId, session.id);
      setResult(r);
      setPhase("results");
    } catch {
      setErrorMsg("Could not submit. Please try again.");
      setPhase("error");
    }
    setSubmitting(false);
  }

  if (phase === "loading" || phase === "redirect") {
    return (
      <div className="text-muted-foreground flex min-h-screen items-center justify-center gap-2 text-sm">
        <Loader2 className="size-4 animate-spin" /> Loading assessment…
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
    return (
      <div className="mx-auto max-w-xl px-4 py-8">
        <h1 className="font-display text-xl font-semibold">Quiz Results</h1>
        <div className="mt-1 flex items-center gap-2 text-sm">
          {passed ? (
            <span className="text-brand flex items-center gap-1 font-medium">
              <CheckCircle2 className="size-4" /> Passed — {Math.round(result.score)}/10
            </span>
          ) : (
            <span className="text-destructive flex items-center gap-1 font-medium">
              <XCircle className="size-4" /> Failed — {Math.round(result.score)}/10
            </span>
          )}
        </div>

        <ul className="mt-6 space-y-4">
          {result.questions.map((rq) => (
            <li
              key={rq.id}
              className={`rounded-xl border p-4 text-sm ${
                rq.is_correct
                  ? "border-green-400 bg-green-50"
                  : "border-red-400 bg-red-50"
              }`}
            >
              <p className="font-medium">{rq.prompt}</p>
              <ul className="mt-2 space-y-1">
                {rq.choices.map((c) => {
                  const isCorrect = rq.correct_answers.includes(c);
                  const chosen = (rq.learner_choice ?? []).includes(c);
                  return (
                    <li
                      key={c}
                      className={`flex items-center gap-2 rounded px-2 py-1 ${
                        isCorrect
                          ? "bg-green-100 text-green-800"
                          : chosen
                            ? "bg-red-100 text-red-700"
                            : "text-foreground"
                      }`}
                    >
                      {isCorrect ? (
                        <CheckCircle2 className="size-3.5 text-green-600 shrink-0" />
                      ) : chosen ? (
                        <XCircle className="size-3.5 text-red-500 shrink-0" />
                      ) : (
                        <span className="size-3.5 shrink-0" />
                      )}
                      {c}
                    </li>
                  );
                })}
              </ul>
            </li>
          ))}
        </ul>

        <div className="mt-8 flex gap-3">
          {passed ? (
            <Button onClick={() => router.push(llmHref)}>Continue to Oral Assessment</Button>
          ) : (
            <>
              <Button variant="outline" onClick={() => router.push(moduleHref)}>
                Return to Module
              </Button>
              <Button
                onClick={() =>
                  router.push(
                    `/chat/${courseId}?feedback=choices&module=${moduleId}`,
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

  // Quiz phase.
  const currentSelections = (q ? (selections[q.id] ?? []) : []);
  return (
    <div className="mx-auto max-w-xl px-4 py-8">
      <Link
        href={moduleHref}
        className="text-muted-foreground hover:text-foreground mb-6 inline-flex items-center gap-1 text-sm"
      >
        <ArrowLeft className="size-4" /> Back to module
      </Link>

      <div className="mb-2 flex items-center justify-between">
        <h1 className="font-display text-xl font-semibold">Quiz</h1>
        <span className="text-muted-foreground text-sm">
          {qIndex + 1} / {questions.length}
        </span>
      </div>

      <div className="bg-muted mb-2 h-1.5 w-full rounded-full">
        <div
          className="bg-brand h-full rounded-full transition-all"
          style={{ width: `${((qIndex + 1) / questions.length) * 100}%` }}
        />
      </div>

      {q && (
        <div className="mt-6">
          <p className="text-foreground mb-4 font-medium">{q.prompt}</p>
          {q.kind === "msq" && (
            <p className="text-muted-foreground mb-3 text-xs">Select all that apply</p>
          )}
          <div className="space-y-2">
            {q.choices.map((c) => (
              <ChoiceOption
                key={c}
                label={c}
                selected={currentSelections.includes(c)}
                disabled={false}
                onClick={() => toggleSelection(c)}
              />
            ))}
          </div>
        </div>
      )}

      <div className="mt-8 flex justify-end">
        <Button onClick={handleNext} disabled={submitting || currentSelections.length === 0}>
          {submitting ? (
            <><Loader2 className="mr-2 size-4 animate-spin" /> Submitting…</>
          ) : isLast ? (
            "Submit Quiz"
          ) : (
            "Next"
          )}
        </Button>
      </div>
    </div>
  );
}
