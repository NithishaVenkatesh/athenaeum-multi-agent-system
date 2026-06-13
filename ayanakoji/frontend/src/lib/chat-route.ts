/**
 * Parse a `/chat` pathname into the active course and sub-page.
 *
 *   /chat                        -> no course (new chat)
 *   /chat/<id>                   -> course <id>, chat page
 *   /chat/<id>/modules           -> course <id>, modules page
 *   /chat/<id>/assessments       -> course <id>, assessments page
 */

export type ChatPage = "chat" | "modules" | "assessments";

export interface ChatRoute {
  courseId: string | null;
  page: ChatPage;
}

const SUB_PAGES: ChatPage[] = ["modules", "assessments"];

export function parseChatRoute(pathname: string): ChatRoute {
  const parts = pathname.split("/").filter(Boolean);
  if (parts[0] !== "chat" || parts.length < 2) {
    return { courseId: null, page: "chat" };
  }
  const sub = SUB_PAGES.find((p) => p === parts[2]);
  return { courseId: parts[1], page: sub ?? "chat" };
}
