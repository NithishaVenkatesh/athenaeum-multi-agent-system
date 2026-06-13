import { BackendStatus } from "@/components/backend-status";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-8 p-8">
      <header className="text-center">
        <p className="text-xs uppercase tracking-[0.2em] text-neutral-400">
          Enterprise Learning Agent
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">Ayanakoji</h1>
        <p className="mt-2 max-w-md text-sm text-neutral-500 dark:text-neutral-400">
          Skeleton shell. Frontend ↔ backend connectivity is live below; agent
          surfaces arrive in later phases.
        </p>
      </header>

      <BackendStatus />
    </main>
  );
}
