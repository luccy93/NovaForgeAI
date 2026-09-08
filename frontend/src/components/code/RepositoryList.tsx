"use client";

import { IndexStatusBadge, type IndexState } from "@/components/code/IndexStatusBadge";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalInput } from "@/components/ui/BrutalInput";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { cn } from "@/lib/utils";
import type { RepositoryOut } from "@/types/code";

export interface RepositoryListItem {
  repository: RepositoryOut;
  indexState: IndexState;
}

export function RepositoryList({
  repositories,
  loading,
  error,
  activeId,
  filter,
  onFilterChange,
  onSelect,
  onRetry,
}: {
  repositories: RepositoryListItem[];
  loading: boolean;
  error: string | null;
  activeId: string | null;
  filter: string;
  onFilterChange: (value: string) => void;
  onSelect: (id: string) => void;
  onRetry: () => void;
}) {
  if (error) {
    return (
      <div className="p-3">
        <BrutalErrorState title="Repositories unavailable" description={error} onRetry={onRetry} />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-outline p-3">
        <BrutalInput
          label="Repository"
          placeholder="Filter repositories"
          value={filter}
          onChange={(e) => onFilterChange(e.target.value)}
          aria-label="Filter repositories"
        />
      </div>
      <div aria-live="polite" className="min-h-0 flex-1 overflow-y-auto">
        {loading && repositories.length === 0 ? (
          <div className="space-y-2 p-3">
            <BrutalSkeleton className="h-12 w-full" label="Loading repositories" />
            <BrutalSkeleton className="h-12 w-full" label="Loading repositories" />
          </div>
        ) : repositories.length === 0 ? (
          <div className="p-3">
            <BrutalEmptyState
              title={filter ? "No matching repositories" : "No repositories"}
              description={
                filter
                  ? "Try a different filter."
                  : "No repositories are available in this workspace yet."
              }
            />
          </div>
        ) : (
          <ul className="divide-y divide-outline-variant">
            {repositories.map(({ repository, indexState }) => (
              <li key={repository.id}>
                <button
                  type="button"
                  onClick={() => onSelect(repository.id)}
                  aria-current={activeId === repository.id ? "page" : undefined}
                  className={cn(
                    "w-full px-3 py-3 text-left transition-colors",
                    activeId === repository.id
                      ? "bg-primary-container/10"
                      : "hover:bg-surface-container-high",
                  )}
                >
                  <span className="block truncate font-mono text-xs font-bold text-on-surface">
                    {repository.name}
                  </span>
                  <span className="mt-1 block truncate font-mono text-[10px] text-on-surface-variant">
                    {repository.full_name}
                  </span>
                  <span className="mt-2 block">
                    <IndexStatusBadge state={indexState} />
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}