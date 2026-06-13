/**
 * Parse a `/chat` pathname into the active course and sub-page.
 *
 *   /chat                        -> no course (new chat)
 *   /chat/<id>                   -> course <id>, chat page
 *   /chat/<id>/assessments       -> course <id>, assessments page
 */

export type ChatPage = "chat" | "assessments";

export interface ChatRoute {
  courseId: string | null;
  page: ChatPage;
}

export function parseChatRoute(pathname: string): ChatRoute {
  const parts = pathname.split("/").filter(Boolean);
  if (parts[0] !== "chat" || parts.length < 2) {
    return { courseId: null, page: "chat" };
  }
  return {
    courseId: parts[1],
    page: parts[2] === "assessments" ? "assessments" : "chat",
  };
}
