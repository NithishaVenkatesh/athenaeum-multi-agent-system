"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { patchCourse, type CourseSummary } from "@/lib/api";

export function RenameCourseDialog({
  course,
  onOpenChange,
  onRenamed,
}: {
  course: CourseSummary | null;
  onOpenChange: (open: boolean) => void;
  onRenamed: () => void;
}) {
  const [saving, setSaving] = useState(false);

  async function save(name: string) {
    if (!course) return;
    const trimmed = name.trim();
    if (!trimmed || trimmed === course.chat_name) {
      onOpenChange(false);
      return;
    }
    setSaving(true);
    try {
      await patchCourse(course.id, { chat_name: trimmed });
      onRenamed();
      onOpenChange(false);
    } catch {
      // Leave the dialog open so the learner can retry.
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={course !== null} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-display text-lg">Rename chat</DialogTitle>
        </DialogHeader>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void save(String(new FormData(event.currentTarget).get("chatName") ?? ""));
          }}
          className="flex flex-col gap-4"
        >
          {/* key resets the uncontrolled field whenever a different chat is edited */}
          <Input
            key={course?.id}
            name="chatName"
            defaultValue={course?.chat_name ?? ""}
            autoFocus
            aria-label="Chat name"
            placeholder="Chat name"
          />
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving}>
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
