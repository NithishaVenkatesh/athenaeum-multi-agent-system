import { WorkspaceChrome } from "@/components/workspace/workspace-chrome";

export default function ChatLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return <WorkspaceChrome>{children}</WorkspaceChrome>;
}
