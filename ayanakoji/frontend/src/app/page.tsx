"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { usePersona } from "@/components/persona-provider";

/** Entry point: route to the workspace if signed in, otherwise to the chooser. */
export default function Home() {
  const { persona, ready } = usePersona();
  const router = useRouter();

  useEffect(() => {
    if (!ready) return;
    router.replace(persona ? "/chat" : "/login");
  }, [ready, persona, router]);

  return (
    <div className="text-muted-foreground flex min-h-dvh items-center justify-center text-sm">
      Loading…
    </div>
  );
}
