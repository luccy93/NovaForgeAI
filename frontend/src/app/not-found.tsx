import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";

export default function NotFound() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-surface p-6">
      <div className="w-full max-w-lg">
        <BrutalEmptyState
          title="Page not found"
          description="The page you requested does not exist or has been moved. Check the URL or return to a known location."
          actions={
            <div className="flex flex-wrap justify-center gap-3">
              <BrutalButton variant="yellow" size="sm" href="/dashboard">
                Go to Dashboard
              </BrutalButton>
              <BrutalButton variant="ghost" size="sm" href="/docs">
                View Documentation
              </BrutalButton>
            </div>
          }
        />
      </div>
    </main>
  );
}
