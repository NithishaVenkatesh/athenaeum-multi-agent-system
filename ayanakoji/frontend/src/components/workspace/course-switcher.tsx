"use client";

/**
 * Top-left chat chooser: a searchable select over the persona's courses, plus a
 * "New chat" entry. The trigger shows the active chat's name (or "New chat").
 */

import { ChevronsUpDown, MessageSquarePlus, MessagesSquare, Pencil } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { RenameCourseDialog } from "@/components/workspace/rename-course-dialog";
import { useWorkspace } from "@/components/workspace/workspace-context";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { parseChatRoute } from "@/lib/chat-route";
import type { CourseSummary } from "@/lib/api";

export function CourseSwitcher() {
  const router = useRouter();
  const pathname = usePathname();
  const { courses, reloadCourses } = useWorkspace();
  const [open, setOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<CourseSummary | null>(null);

  const { courseId } = parseChatRoute(pathname);
  const active = courses.find((course) => course.id === courseId);
  const label = active ? active.chat_name : "New chat";

  function go(href: string) {
    setOpen(false);
    router.push(href);
  }

  function openRename(course: CourseSummary) {
    setOpen(false);
    setRenameTarget(course);
  }

  return (
    <>
      <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={<Button variant="outline" size="sm" aria-label="Choose a chat" />}
      >
        <MessagesSquare className="text-muted-foreground" />
        <span className="max-w-40 truncate">{label}</span>
        <ChevronsUpDown className="text-muted-foreground" />
      </PopoverTrigger>
      <PopoverContent align="start" className="w-72 p-0">
        <Command>
          <CommandInput placeholder="Search chats…" />
          <CommandList>
            <CommandEmpty>No chats yet.</CommandEmpty>
            <CommandGroup heading="Courses">
              {courses.map((course) => (
                <CommandItem
                  key={course.id}
                  value={`${course.chat_name} ${course.id}`}
                  onSelect={() => go(`/chat/${course.id}`)}
                  // This list has no selection checkmark, so suppress CommandItem's
                  // trailing invisible CheckIcon — it otherwise reserves ~16px at the
                  // right edge and pushes the rename pencil off the item's true edge.
                  className="group/item [&>svg:last-child]:hidden"
                >
                  <MessagesSquare className="text-muted-foreground" />
                  <span className="flex-1 truncate">{course.chat_name}</span>
                  <button
                    type="button"
                    aria-label={`Rename ${course.chat_name}`}
                    onPointerDown={(event) => event.stopPropagation()}
                    onClick={(event) => {
                      event.stopPropagation();
                      event.preventDefault();
                      openRename(course);
                    }}
                    className="text-muted-foreground hover:text-foreground hover:bg-background -mr-1 rounded-md p-1 opacity-70 transition hover:opacity-100 focus-visible:opacity-100"
                  >
                    <Pencil className="size-3.5" />
                  </button>
                </CommandItem>
              ))}
            </CommandGroup>
            <CommandSeparator />
            <CommandGroup>
              <CommandItem value="new chat" onSelect={() => go("/chat")}>
                <MessageSquarePlus className="text-brand" />
                New chat
              </CommandItem>
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
      </Popover>

      <RenameCourseDialog
        course={renameTarget}
        onOpenChange={(isOpen) => {
          if (!isOpen) setRenameTarget(null);
        }}
        onRenamed={() => {
          void reloadCourses();
        }}
      />
    </>
  );
}
