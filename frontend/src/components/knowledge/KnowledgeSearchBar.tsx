"use client";

import { useState } from "react";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalInput } from "@/components/ui/BrutalInput";

export function KnowledgeSearchBar({
  initialQuery,
  loading,
  onSearch,
}: {
  initialQuery: string;
  loading: boolean;
  onSearch: (query: string) => void;
}) {
  const [query, setQuery] = useState(initialQuery);
  const [prevInitial, setPrevInitial] = useState(initialQuery);

  // Sync the committed query (e.g. a tenant-switch reset) back into the input,
  // adjusting state during render instead of an effect per React guidance.
  if (prevInitial !== initialQuery) {
    setPrevInitial(initialQuery);
    setQuery(initialQuery);
  }

  function submit() {
    const trimmed = query.trim();
    if (!trimmed || loading) return;
    onSearch(trimmed);
  }

  return (
    <div className="flex items-end gap-2 border-b border-outline p-3">
      <div className="min-w-0 flex-1">
        <BrutalInput
          label="Search knowledge"
          placeholder="Search the knowledge base (hybrid retrieval)"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
          }}
          aria-label="Knowledge search"
        />
      </div>
      <BrutalButton variant="yellow" size="sm" onClick={submit} disabled={loading || !query.trim()}>
        {loading ? "Searching…" : "Search"}
      </BrutalButton>
    </div>
  );
}