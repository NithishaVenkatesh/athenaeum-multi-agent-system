"use client";

/**
 * Workspace state shared across the chat shell: the signed-in persona's list of
 * courses (chats) for the chooser, plus a reload hook the chat page calls after
 * creating or renaming a course so the chooser stays in sync.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { listCourses, type CourseSummary } from "@/lib/api";

interface WorkspaceContextValue {
  personaId: string;
  courses: CourseSummary[];
  loading: boolean;
  reloadCourses: () => Promise<void>;
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function WorkspaceProvider({
  personaId,
  children,
}: {
  personaId: string;
  children: React.ReactNode;
}) {
  const [courses, setCourses] = useState<CourseSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const reloadCourses = useCallback(async () => {
    setLoading(true);
    try {
      setCourses(await listCourses(personaId));
    } catch {
      // Keep the previous list on a transient error.
    } finally {
      setLoading(false);
    }
  }, [personaId]);

  // Initial load. State updates happen inside async callbacks (not synchronously
  // in the effect body) so the list hydrates without a render-cascade warning.
  useEffect(() => {
    let active = true;
    listCourses(personaId)
      .then((next) => {
        if (active) {
          setCourses(next);
          setLoading(false);
        }
      })
      .catch(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [personaId]);

  const value = useMemo(
    () => ({ personaId, courses, loading, reloadCourses }),
    [personaId, courses, loading, reloadCourses],
  );

  return (
    <WorkspaceContext.Provider value={value}>
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace(): WorkspaceContextValue {
  const context = useContext(WorkspaceContext);
  if (!context) {
    throw new Error("useWorkspace must be used within a WorkspaceProvider");
  }
  return context;
}
