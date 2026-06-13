"use client";

import { useState } from "react";

import { Input } from "@/components/ui/input";
import { patchCourse, type Course } from "@/lib/api";

export function RenameTitle({
  course,
  onRenamed,
}: {
  course: Course;
  onRenamed: (course: Course) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(course.chat_name);

  async function save() {
    setEditing(false);
    const text = value.trim();
    if (!text || text === course.chat_name) {
      setValue(course.chat_name);
      return;
    }
    try {
      onRenamed(await patchCourse(course.id, { chat_name: text }));
    } catch {
      setValue(course.chat_name);
    }
  }

  if (editing) {
    return (
      <Input
        autoFocus
        value={value}
        aria-label="Chat name"
        onChange={(event) => setValue(event.target.value)}
        onBlur={save}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            void save();
          } else if (event.key === "Escape") {
            setValue(course.chat_name);
            setEditing(false);
          }
        }}
        className="font-display h-8 max-w-xs text-lg"
      />
    );
  }

  return (
    <button
      type="button"
      onClick={() => setEditing(true)}
      title="Rename chat"
      className="font-display hover:text-brand truncate text-lg tracking-tight transition-colors"
    >
      {course.chat_name}
    </button>
  );
}
