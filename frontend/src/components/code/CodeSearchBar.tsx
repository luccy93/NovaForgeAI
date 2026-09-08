"use client";

import { useState } from "react";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalInput } from "@/components/ui/BrutalInput";

export function CodeSearchBar({
  disabled,
  loading,
  onSearch,
}: {
  disabled: boolean;
  loading: boolean;
  onSearch: (query: string, symbolOnly: boolean) => void;
}) {
  const [query, setQuery] = useState("");
  const [symbolOnly, setSymbolOnly] = useState(false);

  function submit() {
    const trimmed = query.trim();
    if (!trimmed || disabled || loading) return;
    onSearch(trimmed, symbolOnly);
  }

  return (
    <div className="flex items-end gap-2 border-b border-outline p-3">
      <div className="min-w-0 flex-1">
        <BrutalInput
          label="Search code"
          placeholder={symbolOnly ? "Search symbols by name" : "Search indexed code (hybrid)"}
          value={query}
          disabled={disabled}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
          }}
          aria-label="Code search"
        />
      </div>
      <label className="flex items-center gap-2 pb-1 text-label-caps uppercase tracking-widest text-on-surface-variant">
        <input
          type="checkbox"
          checked={symbolOnly}
          disabled={disabled}
          onChange={(e) => setSymbolOnly(e.target.checked)}
          className="h-4 w-4"
        />
        Symbols only
      </label>
      <BrutalButton variant="yellow" size="sm" onClick={submit} disabled={disabled || loading || !query.trim()}>
        {loading ? "Searching…" : "Search"}
      </BrutalButton>
    </div>
  );
}