"use client";

/**
 * Top-left chat chooser: a searchable select over the persona's courses, plus a
 * "New chat" entry. The trigger shows the active chat's name (or "New chat").
 */

import { ChevronsUpDown, MessageSquarePlus, MessagesSquare } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

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

export function CourseSwitcher() {
  const router = useRouter();
  const pathname = usePathname();
  const { courses } = useWorkspace();
  const [open, setOpen] = useState(false);

  const { courseId } = parseChatRoute(pathname);
  const active = courses.find((course) => course.id === courseId);
  const label = active ? active.chat_name : "New chat";

  function go(href: string) {
    setOpen(false);
    router.push(href);
  }

  return (
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
                >
                  <MessagesSquare className="text-muted-foreground" />
                  <span className="truncate">{course.chat_name}</span>
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
  );
}
