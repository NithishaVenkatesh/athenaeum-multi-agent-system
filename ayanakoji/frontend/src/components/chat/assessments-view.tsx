"use client";

/**
 * Assessments surface for a course. Intentionally light for now: the schema and
 * endpoint exist, but no assessments are produced yet, so this shows a designed
 * empty state. When records arrive it lists them (type + practice/evaluation).
 */

import { GraduationCap } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { listAssessments, type Assessment } from "@/lib/api";

export function AssessmentsView({ courseId }: { courseId: string }) {
  const [assessments, setAssessments] = useState<Assessment[] | null>(null);

  useEffect(() => {
    let active = true;
    listAssessments(courseId)
      .then((next) => active && setAssessments(next))
      .catch(() => active && setAssessments([]));
    return () => {
      active = false;
    };
  }, [courseId]);

  const isEmpty = assessments !== null && assessments.length === 0;

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-4 py-10">
      <h1 className="font-display text-2xl tracking-tight">Assessments</h1>
      <p className="text-muted-foreground mt-1 text-sm">
        Practice and evaluation for this course.
      </p>

      {isEmpty ? (
        <div className="border-border mt-8 flex flex-col items-center justify-center rounded-2xl border border-dashed px-6 py-20 text-center">
          <span className="bg-accent text-brand flex size-12 items-center justify-center rounded-full">
            <GraduationCap className="size-6" />
          </span>
          <h2 className="font-display mt-4 text-xl">No assessments yet</h2>
          <p className="text-muted-foreground mt-2 max-w-sm text-pretty text-sm">
            As you work through the material, practice questions and evaluations
            will appear here.
          </p>
        </div>
      ) : (
        <ul className="mt-8 space-y-2">
          {assessments?.map((assessment) => (
            <li
              key={assessment.id}
              className="border-border bg-card flex items-center justify-between rounded-xl border px-4 py-3"
            >
              <span className="text-sm font-medium capitalize">
                {assessment.type} assessment
              </span>
              <Badge variant="secondary">
                {assessment.is_practice ? "Practice" : "Evaluation"}
              </Badge>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
