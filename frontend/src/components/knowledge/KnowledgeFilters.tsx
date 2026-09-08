"use client";

import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalInput } from "@/components/ui/BrutalInput";
import { BrutalSelect } from "@/components/ui/BrutalSelect";
import type { KnowledgeSearchFilterState } from "@/types/knowledge";

const SOURCE_TYPES = [
  "code_intelligence",
  "data_catalog",
  "documents",
  "workflows",
  "incidents",
  "security",
  "conversations",
  "external",
];

const CLASSIFICATIONS = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "SECRET"];

export function KnowledgeFilters({
  filters,
  disabled,
  onChange,
  onClear,
}: {
  filters: KnowledgeSearchFilterState;
  disabled: boolean;
  onChange: (patch: Partial<KnowledgeSearchFilterState>) => void;
  onClear: () => void;
}) {
  const hasFilters = Boolean(filters.source_type || filters.doc_type || filters.classification);
  return (
    <div className="flex flex-wrap items-end gap-3 border-b border-outline p-3">
      <div className="w-52">
        <BrutalSelect
          label="Source type"
          aria-label="Source type filter"
          value={filters.source_type ?? ""}
          disabled={disabled}
          onChange={(e) => onChange({ source_type: e.target.value || undefined })}
          options={[
            { value: "", label: "All sources" },
            ...SOURCE_TYPES.map((s) => ({ value: s, label: s })),
          ]}
        />
      </div>
      <div className="w-44">
        <BrutalInput
          label="Document type"
          aria-label="Document type filter"
          placeholder="e.g. guide, runbook"
          value={filters.doc_type ?? ""}
          disabled={disabled}
          onChange={(e) => onChange({ doc_type: e.target.value.trim() || undefined })}
        />
      </div>
      <div className="w-44">
        <BrutalSelect
          label="Classification"
          aria-label="Classification filter"
          value={filters.classification ?? ""}
          disabled={disabled}
          onChange={(e) => onChange({ classification: e.target.value || undefined })}
          options={[
            { value: "", label: "Any clearance" },
            ...CLASSIFICATIONS.map((c) => ({ value: c, label: c })),
          ]}
        />
      </div>
      <BrutalButton variant="ghost" size="sm" disabled={disabled || !hasFilters} onClick={onClear}>
        Clear filters
      </BrutalButton>
    </div>
  );
}