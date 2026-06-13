import { AssessmentsView } from "@/components/chat/assessments-view";

export default async function AssessmentsPage({
  params,
}: PageProps<"/chat/[courseId]/assessments">) {
  const { courseId } = await params;
  return <AssessmentsView courseId={courseId} />;
}
