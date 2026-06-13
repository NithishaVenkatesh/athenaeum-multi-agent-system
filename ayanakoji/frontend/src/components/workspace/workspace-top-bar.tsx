"use client";

import Link from "next/link";

import { AccountButton } from "@/components/workspace/account-button";
import { CourseSwitcher } from "@/components/workspace/course-switcher";
import { PageSwitcher } from "@/components/workspace/page-switcher";

export function WorkspaceTopBar() {
  return (
    <header className="border-border bg-background/85 sticky top-0 z-40 flex items-center justify-between gap-3 border-b px-4 py-2.5 backdrop-blur-sm">
      <div className="flex items-center gap-3">
        <Link
          href="/chat"
          aria-label="New chat"
          className="font-display text-brand hidden text-xl leading-none sm:block"
        >
          A.
        </Link>
        <CourseSwitcher />
      </div>

      <PageSwitcher />

      <AccountButton />
    </header>
  );
}
