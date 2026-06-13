import { ModuleDetailView } from "@/components/chat/module-detail-view";

export default async function ModulePage({
  params,
}: PageProps<"/chat/[courseId]/modules/[moduleId]">) {
  const { courseId, moduleId } = await params;
  return <ModuleDetailView courseId={courseId} moduleId={moduleId} />;
}
