import { ModulesView } from "@/components/chat/modules-view";

export default async function ModulesPage({
  params,
}: PageProps<"/chat/[courseId]/modules">) {
  const { courseId } = await params;
  return <ModulesView courseId={courseId} />;
}
