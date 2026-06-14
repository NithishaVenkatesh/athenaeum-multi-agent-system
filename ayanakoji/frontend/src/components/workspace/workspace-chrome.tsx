"use client";

/**
 * Chat workspace shell. Guards the route (no persona → /login), then provides
 * workspace state and the persistent top bar around the active page.
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { usePersona } from "@/components/persona-provider";
import { NavigationProgress } from "@/components/workspace/navigation-progress";
import { NotificationsProvider } from "@/components/workspace/notifications-context";
import { WorkspaceProvider } from "@/components/workspace/workspace-context";
import { WorkspaceTopBar } from "@/components/workspace/workspace-top-bar";

export function WorkspaceChrome({ children }: { children: React.ReactNode }) {
  const { persona, ready } = usePersona();
  const router = useRouter();

  useEffect(() => {
    if (ready && !persona) router.replace("/login");
  }, [ready, persona, router]);

  if (!ready || !persona) {
    return (
      <div className="text-muted-foreground flex min-h-dvh items-center justify-center text-sm">
        Loading your workspace…
      </div>
    );
  }

  return (
    <WorkspaceProvider personaId={persona.employee_id}>
      <NotificationsProvider personaId={persona.employee_id}>
        <NavigationProgress>
          <div className="flex min-h-dvh flex-col">
            <WorkspaceTopBar />
            <main className="flex flex-1 flex-col">{children}</main>
          </div>
        </NavigationProgress>
      </NotificationsProvider>
    </WorkspaceProvider>
  );
}
