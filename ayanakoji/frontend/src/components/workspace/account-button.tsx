"use client";

/** Top-right identity chip + sign-out. Sign out clears the persona session. */

import { LogOut } from "lucide-react";
import { useRouter } from "next/navigation";

import { usePersona } from "@/components/persona-provider";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { avatarDataUri } from "@/lib/avatar";

export function AccountButton() {
  const { persona, signOut } = usePersona();
  const router = useRouter();

  if (!persona) return null;

  function handleSignOut() {
    signOut();
    router.replace("/login");
  }

  return (
    <div className="flex items-center gap-2">
      <span className="border-border bg-card flex items-center gap-2 rounded-xl border py-1 pr-3 pl-1">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={avatarDataUri(persona.codename)}
          alt=""
          width={28}
          height={28}
          className="ring-border size-7 rounded-md ring-1"
        />
        <span className="text-sm font-medium">{persona.codename}</span>
        <span className="text-muted-foreground hidden font-mono text-[0.7rem] sm:inline">
          {persona.employee_id}
        </span>
      </span>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                variant="ghost"
                size="icon"
                aria-label="Sign out"
                onClick={handleSignOut}
                className="text-muted-foreground hover:text-foreground"
              >
                <LogOut />
              </Button>
            }
          />
          <TooltipContent>Sign out</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </div>
  );
}
