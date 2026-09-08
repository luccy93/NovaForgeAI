"use client";

import { useState } from "react";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalInput } from "@/components/ui/BrutalInput";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { api, getToken } from "@/lib/api";
import type { ExplainOut } from "@/types/code";
import { asNumber, asRecordList, asString, asStringList, devErrorMessage } from "./dev-utils";

const kindOptions = [
  { id: "file", label: "File" },
  { id: "function", label: "Function" },
  { id: "architecture", label: "Architecture" },
  { id: "dependency", label: "Dependency" },
];

export function DeveloperExplain({ repoId }: { repoId: string }) {
  const [kind, setKind] = useState("file");
  const [target, setTarget] = useState("");
  const [top, setTop] = useState(20);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ExplainOut | null>(null);

  const run = async () => {
    const token = getToken();
    if (!token || !target.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.aiDevExplain(token, {
        repository_id: repoId,
        kind,
        target: target.trim(),
        top,
      });
      setResult(data);
    } catch (e) {
      const msg = devErrorMessage(e, "explanation");
      if (msg) setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-3">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void run();
        }}
      >
        <div className="flex flex-wrap items-end gap-2">
          <label className="sr-only" htmlFor="dev-explain-kind">
            Kind
          </label>
          <select
            id="dev-explain-kind"
            value={kind}
            onChange={(e) => setKind(e.target.value)}
            className="h-12 border border-outline bg-surface px-3 font-mono text-xs text-on-surface outline-none focus:border-primary-container"
          >
            {kindOptions.map((k) => (
              <option key={k.id} value={k.id}>
                {k.label}
              </option>
            ))}
          </select>
          <div className="min-w-48 flex-1">
            <BrutalInput
              id="dev-explain-target"
              label="Target"
              placeholder={kind === "file" ? "src/main.py" : "parse_amount"}
              value={target}
              onChange={(e) => setTarget(e.target.value)}
            />
          </div>
          <div className="w-24">
            <BrutalInput
              id="dev-explain-top"
              label="Top"
              type="number"
              min={1}
              max={50}
              value={String(top)}
              onChange={(e) => setTop(Number(e.target.value) || 20)}
            />
          </div>
          <BrutalButton type="submit" size="sm" disabled={loading || !target.trim()}>
            {loading ? "Explaining…" : "Explain"}
          </BrutalButton>
        </div>
      </form>

      {loading ? <BrutalSkeleton className="h-32 w-full" label="Generating explanation" /> : null}
      {error ? (
        <BrutalErrorState title="Explanation unavailable" description={error} onRetry={() => void run()} />
      ) : null}
      {result && !loading ? <ExplainResult data={result} /> : null}
    </div>
  );
}

function ExplainResult({ data }: { data: ExplainOut }) {
  switch (data.kind) {
    case "file":
      return <FileExplanation data={data} />;
    case "function":
      return <FunctionExplanation data={data} />;
    case "architecture":
      return <ArchitectureExplanation data={data} />;
    case "dependency":
      return <DependencyExplanation data={data} />;
    default:
      return (
        <pre className="max-h-64 overflow-auto whitespace-pre-wrap border border-outline bg-surface p-3 font-mono text-[11px] text-on-surface">
          {JSON.stringify(data, null, 2)}
        </pre>
      );
  }
}

function FileExplanation({ data }: { data: ExplainOut }) {
  const filePath = asString(data.file_path) ?? "";
  const snippets = asRecordList(data.snippets);
  return (
    <div className="space-y-3">
      <dl className="grid grid-cols-2 gap-2">
        <Stat label="File" value={filePath} />
        <Stat label="Language" value={asString(data.language) ?? ""} />
        <Stat label="Lines" value={asNumber(data.line_count) != null ? String(asNumber(data.line_count)) : ""} />
        <Stat label="Symbols" value={String(asRecordList(data.symbols).length)} />
      </dl>
      <div>
        <h3 className="font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">Symbols</h3>
        {asRecordList(data.symbols).length === 0 ? (
          <p className="font-mono text-[11px] text-on-surface-variant">No symbols described.</p>
        ) : (
          <ul className="mt-1 space-y-1">
            {asRecordList(data.symbols).map((s, i) => (
              <li key={i} className="border border-outline bg-surface p-2 font-mono text-[11px] text-on-surface-variant">
                {asString(s.name) ?? "?"} ({asString(s.type) ?? "symbol"})
                {asNumber(s.line_start) != null ? (
                  <span className="ml-1 text-on-surface-variant/70">
                    lines {asNumber(s.line_start)}–{asNumber(s.line_end) ?? asNumber(s.line_start)}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>
      <ListBlock title="Imports" items={asStringList(data.imports)} empty="No imports described." />
      {snippets.length > 0 ? (
        <div>
          <h3 className="font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">Snippets</h3>
          <ul className="mt-1 space-y-1">
            {snippets.map((s, i) => (
              <li key={i}>
                <pre className="overflow-auto whitespace-pre border border-outline bg-surface p-3 font-mono text-[11px] text-on-surface">
                  {asString(s.content) ?? ""}
                </pre>
                {asNumber(s.line_start) != null ? (
                  <p className="mt-0.5 font-mono text-[10px] text-on-surface-variant">
                    lines {asNumber(s.line_start)}–{asNumber(s.line_end) ?? asNumber(s.line_start)}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function FunctionExplanation({ data }: { data: ExplainOut }) {
  const matches = asRecordList(data.matches);
  const callSites = asRecordList(data.call_sites);
  return (
    <div className="space-y-3">
      <dl className="grid grid-cols-2 gap-2">
        <Stat label="Function" value={asString(data.name) ?? ""} />
        <Stat label="Matches" value={String(matches.length)} />
      </dl>
      <div>
        <h3 className="font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">Matches</h3>
        {matches.length === 0 ? (
          <p className="font-mono text-[11px] text-on-surface-variant">No matches found.</p>
        ) : (
          <ul className="mt-1 space-y-1">
            {matches.map((m, i) => (
              <li key={i} className="border border-outline bg-surface p-2 font-mono text-[11px] text-on-surface-variant">
                {asString(m.file_path) ?? "?"}:{asNumber(m.line_start) ?? asString(m.line_start) ?? "?"}
                {" — "}
                {asString(m.name) ?? "?"}
                {asString(m.uncertain) ? " (uncertain)" : ""}
              </li>
            ))}
          </ul>
        )}
      </div>
      <ListBlock
        title="Call sites"
        items={callSites.map(
          (c) => `${asString(c.file_path) ?? "?"}:${asNumber(c.line_start) ?? asString(c.line_start) ?? "?"} — ${asString(c.name) ?? "?"}`,
        )}
        empty="No call sites found."
      />
      {asString(data.uncertain) ? (
        <p className="font-mono text-[11px] text-yellow-700">{asString(data.uncertain)}</p>
      ) : null}
    </div>
  );
}

function ArchitectureExplanation({ data }: { data: ExplainOut }) {
  const symbolsByType = asRecordList(data.symbols_by_type);
  const moduleEdges = asRecordList(data.module_edges);
  return (
    <div className="space-y-3">
      <dl className="grid grid-cols-2 gap-2">
        <Stat label="Files" value={asNumber(data.file_count) != null ? String(asNumber(data.file_count)) : ""} />
        <Stat label="Modules" value={String(symbolsByType.length)} />
      </dl>
      <ListBlock
        title="Module edges"
        items={moduleEdges.map((e) => `${asString(e.source) ?? "?"} → ${asString(e.target) ?? "?"}`)}
        empty="No module edges described."
      />
      <ListBlock
        title="Symbols by type"
        items={asStringList(data.symbols_by_type)}
        empty="No symbol breakdown described."
      />
      {asString(data.uncertain) ? (
        <p className="font-mono text-[11px] text-yellow-700">{asString(data.uncertain)}</p>
      ) : null}
    </div>
  );
}

function DependencyExplanation({ data }: { data: ExplainOut }) {
  const imports = asStringList(data.imports);
  const count = asNumber(data.count);
  return (
    <div className="space-y-3">
      <dl className="grid grid-cols-2 gap-2">
        <Stat label="File" value={asString(data.file_path) ?? ""} />
        <Stat label="Deps" value={count != null ? String(count) : String(imports.length)} />
      </dl>
      <ListBlock title="Imports" items={imports} empty="No imports described." />
      {asString(data.uncertain) ? (
        <p className="font-mono text-[11px] text-yellow-700">{asString(data.uncertain)}</p>
      ) : null}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-outline bg-surface p-2">
      <dt className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">{label}</dt>
      <dd className="mt-0.5 break-words font-mono text-xs font-bold text-on-surface">{value || "—"}</dd>
    </div>
  );
}

function ListBlock({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <div>
      <h3 className="font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">{title}</h3>
      {items.length === 0 ? (
        <p className="mt-1 font-mono text-[11px] text-on-surface-variant">{empty}</p>
      ) : (
        <ul className="mt-1 space-y-1">
          {items.map((item, i) => (
            <li key={i} className="border border-outline bg-surface p-2 font-mono text-[11px] text-on-surface-variant">
              {item}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}