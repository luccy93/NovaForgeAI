"use client";

import { useEffect, useMemo, useState } from "react";
import { highlightCode, detectLanguage, type HighlightResult } from "@/lib/highlight";

export function CodePreview({
  code,
  filePath,
  languageHint,
  startLine = 1,
  maxLines = 200,
}: {
  code: string;
  filePath?: string | null;
  languageHint?: string | null;
  startLine?: number;
  maxLines?: number;
}) {
  const [result, setResult] = useState<HighlightResult | null>(null);

  const language = useMemo(
    () => detectLanguage(filePath ?? null, languageHint ?? null),
    [filePath, languageHint],
  );

  // Bound the snippet — only render what the backend supplied, truncated.
  const bounded = useMemo(() => {
    const lines = code.split("\n");
    if (lines.length > maxLines) {
      return lines.slice(0, maxLines).join("\n");
    }
    return code;
  }, [code, maxLines]);

  useEffect(() => {
    let active = true;
    void highlightCode(bounded, language).then((r) => {
      if (active) setResult(r);
    });
    return () => {
      active = false;
    };
  }, [bounded, language]);

  const lines: HighlightResult["lines"] = result?.lines ?? [{ tokens: [{ content: bounded, color: null }] }];
  const highlighted = result?.highlighted ?? false;

  return (
    <div
      role="region"
      aria-label={`Code preview${language ? ` (${language})` : ""}`}
      className="overflow-x-auto border border-outline bg-[#24292e] text-[12px] leading-relaxed"
    >
      <pre className="min-w-max p-3">
        <code className="whitespace-pre">
          {lines.map((line, i) => (
            <span className="flex" key={i}>
              {startLine ? (
                <span
                  aria-hidden="true"
                  className="mr-4 inline-block w-8 shrink-0 select-none text-right text-on-surface-variant/60"
                >
                  {startLine + i}
                </span>
              ) : null}
              <span className={highlighted ? "text-[#e1e4e8]" : "whitespace-pre text-on-surface"}>
                {line.tokens.length === 0 ? "\u00A0" : null}
                {line.tokens.map((token, j) => (
                  <span key={j} style={token.color ? { color: token.color } : undefined}>
                    {token.content}
                  </span>
                ))}
              </span>
            </span>
          ))}
        </code>
      </pre>
    </div>
  );
}