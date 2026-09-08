"use client";

// Read-only syntax highlighting for backend-provided code snippets.
//
// SECURITY: this module returns plain text + color tokens. It NEVER returns
// raw HTML and NEVER uses dangerouslySetInnerHTML. The caller renders tokens
// as React text nodes, which escape automatically. Unknown/unsupported
// languages fall back to plain-text rendering with no highlighting library.

export interface HighlightToken {
  content: string;
  color?: string | null;
}

export interface HighlightLine {
  tokens: HighlightToken[];
}

export interface HighlightResult {
  lines: HighlightLine[];
  /** False when the snippet fell back to plain rendering (unknown language). */
  highlighted: boolean;
  backgroundColor?: string | null;
  foregroundColor?: string | null;
}

const SUPPORTED_LANGS = new Set([
  "python",
  "javascript",
  "typescript",
  "jsx",
  "tsx",
  "json",
  "html",
  "css",
  "sql",
  "bash",
  "markdown",
  "yaml",
  "toml",
  "java",
  "go",
  "rust",
  "c",
  "cpp",
  "ruby",
  "php",
  "shell",
]);

const EXT_TO_LANG: Record<string, string> = {
  ".py": "python",
  ".pyi": "python",
  ".js": "javascript",
  ".mjs": "javascript",
  ".cjs": "javascript",
  ".jsx": "jsx",
  ".ts": "typescript",
  ".mts": "typescript",
  ".cts": "typescript",
  ".tsx": "tsx",
  ".json": "json",
  ".html": "html",
  ".htm": "html",
  ".css": "css",
  ".scss": "css",
  ".less": "css",
  ".sql": "sql",
  ".sh": "bash",
  ".bash": "bash",
  ".zsh": "bash",
  ".md": "markdown",
  ".markdown": "markdown",
  ".yaml": "yaml",
  ".yml": "yaml",
  ".toml": "toml",
  ".java": "java",
  ".kt": "kotlin",
  ".go": "go",
  ".rs": "rust",
  ".c": "c",
  ".h": "c",
  ".cpp": "cpp",
  ".cc": "cpp",
  ".hpp": "cpp",
  ".rb": "ruby",
  ".php": "php",
};

export function detectLanguage(filePath: string | null | undefined, hint?: string | null): string | null {
  if (filePath) {
    const lower = filePath.toLowerCase();
    for (const ext of Object.keys(EXT_TO_LANG)) {
      if (lower.endsWith(ext)) return EXT_TO_LANG[ext];
    }
  }
  if (hint) {
    const h = hint.toLowerCase();
    if (SUPPORTED_LANGS.has(h)) return h;
  }
  return null;
}

export function isLanguageSupported(language: string | null | undefined): boolean {
  return !!language && SUPPORTED_LANGS.has(language);
}

const memo = new Map<string, HighlightResult>();

function hashString(value: string): string {
  let hash = 0;
  for (let i = 0; i < value.length; i++) {
    hash = (hash << 5) - hash + value.charCodeAt(i);
    hash |= 0;
  }
  return String(hash);
}

function plainResult(code: string): HighlightResult {
  const lines = code.split("\n").map((line) => ({ tokens: [{ content: line, color: null }] }));
  return { lines, highlighted: false, backgroundColor: null, foregroundColor: null };
}

let highlighterPromise: Promise<(typeof import("shiki"))["createHighlighter"] | null> | null = null;
const highlighterCache = new Map<string, Awaited<ReturnType<(typeof import("shiki"))["createHighlighter"]>> | null>();

function getCreateHighlighter(): Promise<(typeof import("shiki"))["createHighlighter"] | null> {
  if (!highlighterPromise) {
    highlighterPromise = import("shiki")
      .then((mod) => mod.createHighlighter ?? null)
      .catch(() => null);
  }
  return highlighterPromise;
}

async function getHighlighter(
  language: string,
): Promise<Awaited<ReturnType<(typeof import("shiki"))["createHighlighter"]>> | null> {
  const cached = highlighterCache.get(language);
  if (cached !== undefined) return cached;
  const createHighlighter = await getCreateHighlighter();
  if (!createHighlighter) {
    highlighterCache.set(language, null);
    return null;
  }
  try {
    const { createJavaScriptRegexEngine } = await import("shiki");
    const engine = createJavaScriptRegexEngine();
    const highlighter = await createHighlighter({
      langs: [language],
      themes: ["github-dark"],
      engine,
    });
    highlighterCache.set(language, highlighter);
    return highlighter;
  } catch {
    highlighterCache.set(language, null);
    return null;
  }
}

/**
 * Highlight backend-provided code snippets. Returns token lines for React
 * rendering (never raw HTML). Falls back to plain lines when the language is
 * unsupported or the highlighter fails to load — never throws.
 */
export async function highlightCode(code: string, language: string | null): Promise<HighlightResult> {
  if (!language || !SUPPORTED_LANGS.has(language)) {
    return plainResult(code);
  }
  const key = `${language}::${code.length}::${hashString(code)}`;
  const hit = memo.get(key);
  if (hit !== undefined) return hit;

  try {
    const highlighter = await getHighlighter(language);
    if (!highlighter) {
      const fallback = plainResult(code);
      memo.set(key, fallback);
      return fallback;
    }
    const tokensResult = highlighter.codeToTokens(
      code,
      { lang: language, theme: "github-dark" } as Parameters<typeof highlighter.codeToTokens>[1],
    );
    const lines: HighlightLine[] = (tokensResult.tokens ?? []).map((line) => ({
      tokens: line.map((t) => ({ content: t.content, color: t.color ?? null })),
    }));
    const result: HighlightResult = {
      lines,
      highlighted: true,
      backgroundColor: tokensResult.bg ?? null,
      foregroundColor: tokensResult.fg ?? null,
    };
    memo.set(key, result);
    return result;
  } catch {
    const fallback = plainResult(code);
    memo.set(key, fallback);
    return fallback;
  }
}

export function __resetHighlightMemo() {
  memo.clear();
  highlighterPromise = null;
  highlighterCache.clear();
}