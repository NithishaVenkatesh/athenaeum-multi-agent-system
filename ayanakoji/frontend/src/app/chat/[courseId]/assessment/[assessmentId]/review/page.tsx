"use client";

/**
 * Read-only review of a completed evaluation, reached from the Evaluations tab.
 * Reuses GET /results, which reveals correct answers (choices) or the examiner's
 * reasoning + transcript (oral). No answering happens here — it is a record.
 */

import { ArrowLeft, CheckCircle2, Loader2, XCircle } from "lucide-react";
import Link from "next/link";
import { use, useEffect, useState } from "react";

import {
  getAssessmentResults,
  type ChoiceQuestionResult,
  type ChoiceSubmitResult,
  type LlmQuestionResult,
  type LlmSubmitResult,
} from "@/lib/api";

type Result = ChoiceSubmitResult | LlmSubmitResult;

function isChoices(r: Result): r is ChoiceSubmitResult {
  return r.questions.length > 0 && "choices" in r.questions[0];
}

function ScoreHeader({ title, score, passed }: { title: string; score: number; passed: boolean }) {
  return (
    <>
      <h1 className="font-display text-xl font-semibold">{title}</h1>
      <div className="mt-1 flex items-center gap-2 text-sm">
        {passed ? (
          <span className="text-brand flex items-center gap-1 font-medium">
            <CheckCircle2 className="size-4" /> Passed — {Math.round(score)}/10
          </span>
        ) : (
          <span className="text-destructive flex items-center gap-1 font-medium">
            <XCircle className="size-4" /> Failed — {Math.round(score)}/10
          </span>
        )}
      </div>
    </>
  );
}

function ChoiceReview({ questions }: { questions: ChoiceQuestionResult[] }) {
  return (
    <ul className="mt-6 space-y-4">
      {questions.map((rq) => (
        <li
          key={rq.id}
          className={`rounded-xl border p-4 text-sm ${
            rq.is_correct ? "border-green-400 bg-green-50" : "border-red-400 bg-red-50"
          }`}
        >
          <p className="font-medium">{rq.prompt}</p>
          <ul className="mt-2 space-y-1">
            {rq.choices.map((c) => {
              const correct = rq.correct_answers.includes(c);
              const chosen = (rq.learner_choice ?? []).includes(c);
              return (
                <li
                  key={c}
                  className={`flex items-center gap-2 rounded px-2 py-1 ${
                    correct
                      ? "bg-green-100 text-green-800"
                      : chosen
                        ? "bg-red-100 text-red-700"
                        : "text-foreground"
                  }`}
                >
                  {correct ? (
                    <CheckCircle2 className="size-3.5 shrink-0 text-green-600" />
                  ) : chosen ? (
                    <XCircle className="size-3.5 shrink-0 text-red-500" />
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
  );
}

function LlmReview({ questions }: { questions: LlmQuestionResult[] }) {
  return (
    <div className="mt-6 space-y-6">
      {questions.map((q) => (
        <div key={q.id} className="border-border rounded-xl border p-4 text-sm">
          <p className="font-medium">{q.prompt}</p>
          {q.reasoning && (
            <div className="bg-muted/60 mt-3 rounded-lg p-3">
              <p className="text-muted-foreground mb-1 text-xs font-medium uppercase tracking-wide">
                Examiner feedback — {q.score ?? "—"}/10
              </p>
              <p>{q.reasoning}</p>
            </div>
          )}
          {q.messages.length > 0 && (
            <div className="mt-3 space-y-2">
              {q.messages.map((m, i) => (
                <div
                  key={i}
                  className={`rounded-lg px-3 py-2 text-xs ${
                    m.role === "assistant"
                      ? "bg-muted text-foreground"
                      : "bg-brand/10 text-foreground"
                  }`}
                >
                  <span className="text-muted-foreground mr-1 font-medium">
                    {m.role === "assistant" ? "Examiner:" : "You:"}
                  </span>
                  {m.content}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

export default function ReviewPage({
  params,
}: {
  params: Promise<{ courseId: string; assessmentId: string }>;
}) {
  const { courseId, assessmentId } = use(params);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    getAssessmentResults(courseId, assessmentId, controller.signal)
      .then(setResult)
      .catch(() => {
        if (!controller.signal.aborted) setError("Could not load this review.");
      });
    return () => controller.abort();
  }, [courseId, assessmentId]);

  const evaluationsHref = `/chat/${courseId}/assessments`;

  if (error) {
    return (
      <div className="mx-auto max-w-xl px-4 py-16 text-center">
        <p className="text-destructive text-sm">{error}</p>
        <Link href={evaluationsHref} className="text-brand mt-4 inline-block text-sm">
          Back to evaluations
        </Link>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="text-muted-foreground flex min-h-screen items-center justify-center gap-2 text-sm">
        <Loader2 className="size-4 animate-spin" /> Loading review…
      </div>
    );
  }

  const choices = isChoices(result);

  return (
    <div className="mx-auto max-w-xl px-4 py-8">
      <Link
        href={evaluationsHref}
        className="text-muted-foreground hover:text-foreground mb-6 inline-flex items-center gap-1 text-sm"
      >
        <ArrowLeft className="size-4" /> Back to evaluations
      </Link>

      <ScoreHeader
        title={choices ? "Quiz Review" : "Oral Exam Review"}
        score={result.score}
        passed={result.passed}
      />

      {choices ? (
        <ChoiceReview questions={(result as ChoiceSubmitResult).questions} />
      ) : (
        <LlmReview questions={(result as LlmSubmitResult).questions} />
      )}
    </div>
  );
}
