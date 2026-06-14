import { ChatView } from "@/components/chat/chat-view";

export default async function CoursePage({
  params,
  searchParams,
}: PageProps<"/chat/[courseId]"> & {
  searchParams?: Promise<{ feedback?: string; module?: string }>;
}) {
  const { courseId } = await params;
  const sp = searchParams ? await searchParams : {};

  // The "Get Feedback" button lands here with ?feedback=choices|llm&module=<id>.
  // We hand ChatView a structured request so it streams grounded feedback via the
  // dedicated endpoint (which bypasses the topic gate) instead of a chat message
  // that the grounding layer would refuse as off-syllabus.
  const kind: "choices" | "llm" | undefined =
    sp.feedback === "choices" || sp.feedback === "llm" ? sp.feedback : undefined;
  const moduleId = sp.module;
  const feedback = kind && moduleId ? { kind, moduleId } : undefined;

  return <ChatView courseId={courseId} feedback={feedback} />;
}
