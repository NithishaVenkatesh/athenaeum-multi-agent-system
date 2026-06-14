"use client";

import type * as React from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { DayPicker } from "react-day-picker";
import "react-day-picker/style.css";

import { cn } from "@/lib/utils";

export type CalendarProps = React.ComponentProps<typeof DayPicker>;

// react-day-picker ships its own layout CSS; we only retint it to the design tokens
// (brand accent, surface-matched sizing) so the calendar reads as part of the system.
const THEME = {
  "--rdp-accent-color": "var(--brand)",
  "--rdp-accent-background-color": "var(--accent)",
  "--rdp-today-color": "var(--brand)",
  "--rdp-day-width": "2.2rem",
  "--rdp-day-height": "2.2rem",
  "--rdp-day_button-border-radius": "0.5rem",
  "--rdp-selected-border": "none",
  "--rdp-outside-opacity": "0.4",
} as React.CSSProperties;

/** Shadcn-style single/range calendar, themed to the Athenaeum tokens. */
export function Calendar({ className, style, ...props }: CalendarProps) {
  return (
    <DayPicker
      className={cn("p-2 text-sm", className)}
      style={{ ...THEME, ...style }}
      components={{
        Chevron: ({ orientation, className: cls }) =>
          orientation === "left" ? (
            <ChevronLeft className={cn("size-4", cls)} />
          ) : (
            <ChevronRight className={cn("size-4", cls)} />
          ),
      }}
      {...props}
    />
  );
}
