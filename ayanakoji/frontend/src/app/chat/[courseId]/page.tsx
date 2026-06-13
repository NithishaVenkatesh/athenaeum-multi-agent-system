import { ChatView } from "@/components/chat/chat-view";

export default async function CoursePage({
  params,
}: PageProps<"/chat/[courseId]">) {
  const { courseId } = await params;
  return <ChatView courseId={courseId} />;
}
