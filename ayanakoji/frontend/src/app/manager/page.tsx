"use client";

/**
 * The manager section route. Opens directly (no auth) when a manager persona is
 * selected on the front page; guards against a non-manager landing here by URL.
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { ManagerWorkspace } from "@/components/manager/manager-workspace";
import { usePersona } from "@/components/persona-provider";

export default function ManagerPage() {
  const router = useRouter();
  const { persona, ready } = usePersona();

  const allowed = persona?.is_manager ?? false;

  useEffect(() => {
    if (ready && !allowed) {
      router.replace("/login");
    }
  }, [ready, allowed, router]);

  if (!ready || !persona || !allowed) {
    return null;
  }

  return <ManagerWorkspace employeeId={persona.employee_id} />;
}
