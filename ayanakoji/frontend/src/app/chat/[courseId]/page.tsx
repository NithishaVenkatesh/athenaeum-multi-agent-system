import { ChatView } from "@/components/chat/chat-view";

export default async function CoursePage({
  params,
  searchParams,
}: PageProps<"/chat/[courseId]"> & {
  searchParams?: Promise<{ feedback?: string; module?: string }>;
}) {
  const { courseId } = await params;
  const sp = searchParams ? await searchParams : {};
  const feedbackKind = sp.feedback;
  const feedbackModule = sp.module;

  let initialMessage: string | undefined;
  if (feedbackKind && feedbackModule) {
    const kind = feedbackKind === "choices" ? "quiz" : "oral examination";
    initialMessage = `I just failed the ${kind} assessment for module ${feedbackModule}. Can you help me understand what topics I should focus on and why I may have gone wrong?`;
  }

  return <ChatView courseId={courseId} initialMessage={initialMessage} />;
}
