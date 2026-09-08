"use client";

/* eslint-disable react-hooks/set-state-in-effect -- must clear stale tenant/workspace data synchronously on context switch */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CodeSearchBar } from "@/components/code/CodeSearchBar";
import { CodeViewer } from "@/components/code/CodeViewer";
import { DeveloperPanel } from "@/components/code/DeveloperPanel";
import { IntelligencePanel } from "@/components/code/IntelligencePanel";
import { RepositoryList, type RepositoryListItem } from "@/components/code/RepositoryList";
import { SearchResults } from "@/components/code/SearchResults";
import { SymbolDetailPanel } from "@/components/code/SymbolDetailPanel";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { api, clearToken, getToken } from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import type {
  CodeIndexOut,
  FileContentOut,
  RepositoryOut,
  SearchOut,
  SymbolDetailOut,
  SymbolOut,
} from "@/types/code";
import type { IndexState } from "@/components/code/IndexStatusBadge";

function sessionExpired() {
  clearToken();
  window.location.href = "/auth/login";
}

export function CodeWorkspace() {
  const [repos, setRepos] = useState<RepositoryListItem[]>([]);
  const [reposLoading, setReposLoading] = useState(true);
  const [reposError, setReposError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  const [activeRepoId, setActiveRepoId] = useState<string | null>(null);
  const [activeRepo, setActiveRepo] = useState<RepositoryOut | null>(null);
  const [index, setIndex] = useState<CodeIndexOut | null>(null);
  const [indexState, setIndexState] = useState<IndexState>("unavailable");
  const [, setIndexLoading] = useState(false);

  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [search, setSearch] = useState<SearchOut | null>(null);
  const [symbolResults, setSymbolResults] = useState<SymbolOut[] | null>(null);

  const [fileDetail, setFileDetail] = useState<FileContentOut | null>(null);
  const [fileLoading, setFileLoading] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const [activeFileHit, setActiveFileHit] = useState<SearchOut["results"][number] | null>(null);

  const [activeSymbol, setActiveSymbol] = useState<SymbolOut | null>(null);
  const [symbolDetail, setSymbolDetail] = useState<SymbolDetailOut | null>(null);
  const [symbolLoading, setSymbolLoading] = useState(false);
  const [symbolError, setSymbolError] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const repoSwitchRef = useRef(0);

  const resetAllState = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    repoSwitchRef.current += 1;
    setActiveRepoId(null);
    setActiveRepo(null);
    setIndex(null);
    setIndexState("unavailable");
    setSearch(null);
    setSymbolResults(null);
    setSearchError(null);
    setFileDetail(null);
    setFileError(null);
    setFileLoading(false);
    setActiveFileHit(null);
    setActiveSymbol(null);
    setSymbolDetail(null);
    setSymbolError(null);
    setSymbolLoading(false);
  }, []);

  const loadIndexStates = useCallback(async (token: string, items: RepositoryListItem[]) => {
    // Resolve each repo's index state independently so badges appear as they
    // settle instead of waiting for all requests.
    for (const { repository } of items) {
      let state: IndexState = "unavailable";
      try {
        const idx = await api.ciGetIndex(token, repository.id);
        state = idx.status === "ready" ? "ready" : idx.status === "failed" ? "failed" : "indexing";
      } catch (e) {
        if (e instanceof ApiError) {
          if (e.status === 404) state = "no-data";
          else if (e.kind === "forbidden") state = "unavailable";
          else state = "unavailable";
        }
      }
      setRepos((prev) =>
        prev.map((p) => (p.repository.id === repository.id ? { ...p, indexState: state } : p)),
      );
    }
  }, []);

  const loadRepositories = useCallback(async () => {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setReposLoading(true);
    setReposError(null);
    try {
      const res = await api.listRepositories(token, 100, 0);
      const items: RepositoryListItem[] = (Array.isArray(res) ? res : []).map((r) => ({
        repository: r,
        indexState: "loading",
      }));
      setRepos(items);
      // Resolve index states lazily per repo (only fetch for visible ones).
      await loadIndexStates(token, items);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setReposError(e instanceof Error ? e.message : "Failed to load repositories");
    } finally {
      setReposLoading(false);
    }
  }, [loadIndexStates]);

  // Initial load + context switch handling.
  useEffect(() => {
    void loadRepositories();
    const handler = () => {
      resetAllState();
      setRepos([]);
      void loadRepositories();
    };
    window.addEventListener("tenant:switched", handler as EventListener);
    window.addEventListener("workspace:switched", handler as EventListener);
    return () => {
      window.removeEventListener("tenant:switched", handler as EventListener);
      window.removeEventListener("workspace:switched", handler as EventListener);
    };
  }, [loadRepositories, resetAllState]);

  // Terminate any in-flight request on unmount.
  useEffect(() => {
    return () => {
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
    };
  }, []);

  const selectRepository = useCallback(async (id: string) => {
    const token = getToken();
    if (!token || !id) return;
    if (activeRepoId === id) return;
    repoSwitchRef.current += 1;
    const seq = repoSwitchRef.current;
    if (abortRef.current) abortRef.current.abort();
    abortRef.current = new AbortController();

    setActiveRepoId(id);
    setSearch(null);
    setSymbolResults(null);
    setSearchError(null);
    setFileDetail(null);
    setFileError(null);
    setActiveFileHit(null);
    setActiveSymbol(null);
    setSymbolDetail(null);
    setSymbolError(null);

    try {
      const repo = await api.getRepository(token, id);
      if (seq !== repoSwitchRef.current) return;
      setActiveRepo(repo);

      setIndexLoading(true);
      setIndexState("loading");
      try {
        const idx = await api.ciGetIndex(token, id);
        if (seq !== repoSwitchRef.current) return;
        setIndex(idx);
        setIndexState(idx.status === "ready" ? "ready" : idx.status === "failed" ? "failed" : "stale");
      } catch (e) {
        if (seq !== repoSwitchRef.current) return;
        if (e instanceof ApiError && e.status === 404) setIndexState("no-data");
        else setIndexState("unavailable");
      } finally {
        if (seq === repoSwitchRef.current) setIndexLoading(false);
      }
    } catch (e) {
      if (seq !== repoSwitchRef.current) return;
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setFileError(e instanceof Error ? e.message : "Failed to load repository");
    }
  }, [activeRepoId]);

  const handleSearch = useCallback(
    async (query: string, symbolOnly: boolean) => {
      const token = getToken();
      if (!token || !activeRepoId) return;
      const seq = repoSwitchRef.current;
      setSearchLoading(true);
      setSearchError(null);
      setActiveFileHit(null);
      setFileDetail(null);
      setFileError(null);
      try {
        if (symbolOnly) {
          const res = await api.ciSymbolSearch(token, activeRepoId, query);
          if (seq !== repoSwitchRef.current) return;
          setSymbolResults(res.results ?? []);
          setSearch(null);
        } else {
          const res = await api.ciSearch(token, activeRepoId, query, { maxResults: 30 });
          if (seq !== repoSwitchRef.current) return;
          setSearch(res);
          setSymbolResults(null);
        }
      } catch (e) {
        if (seq !== repoSwitchRef.current) return;
        if (e instanceof ApiError && e.kind === "unauthorized") {
          sessionExpired();
          return;
        }
        setSearchError(e instanceof Error ? e.message : "Search failed");
      } finally {
        if (seq === repoSwitchRef.current) setSearchLoading(false);
      }
    },
    [activeRepoId],
  );

  const openResult = useCallback(
    async (hit: SearchOut["results"][number]) => {
      const token = getToken();
      if (!token || !activeRepoId) return;
      const seq = repoSwitchRef.current;
      setActiveFileHit(hit);
      setActiveSymbol(null);
      setSymbolDetail(null);
      setFileDetail(null);
      setFileError(null);
      setFileLoading(true);
      if (hit.id) {
        try {
          const detail = await api.ciFileDetail(token, activeRepoId, hit.id);
          if (seq === repoSwitchRef.current) setFileDetail(detail);
        } catch (e) {
          if (seq !== repoSwitchRef.current) return;
          if (e instanceof ApiError && e.kind === "unauthorized") {
            sessionExpired();
            return;
          }
          // The hit already carries snippet/context; continue with partial view.
          setFileError(e instanceof Error ? e.message : "File intelligence unavailable");
        } finally {
          if (seq === repoSwitchRef.current) setFileLoading(false);
        }
      } else {
        // Search hits that carry no file id still show preview + line info.
        setFileLoading(false);
      }
    },
    [activeRepoId],
  );

  const selectSymbol = useCallback(
    async (symbol: SymbolOut) => {
      const token = getToken();
      if (!token || !activeRepoId) return;
      const seq = repoSwitchRef.current;
      setActiveSymbol(symbol);
      setActiveFileHit(null);
      setFileDetail(null);
      setSymbolLoading(true);
      setSymbolError(null);
      try {
        const detail = await api.ciSymbolDetail(token, activeRepoId, symbol.id);
        if (seq === repoSwitchRef.current) setSymbolDetail(detail);
      } catch (e) {
        if (seq !== repoSwitchRef.current) return;
        if (e instanceof ApiError && e.kind === "unauthorized") {
          sessionExpired();
          return;
        }
        setSymbolError(e instanceof Error ? e.message : "Symbol detail unavailable");
      } finally {
        if (seq === repoSwitchRef.current) setSymbolLoading(false);
      }
    },
    [activeRepoId],
  );

  const openSymbolById = useCallback(
    (symbolId: string) => {
      const sym = (symbolResults ?? []).find((s) => s.id === symbolId);
      if (sym) void selectSymbol(sym);
    },
    [symbolResults, selectSymbol],
  );

  const rebuildIndex = useCallback(async () => {
    const token = getToken();
    if (!token || !activeRepoId) return;
    const seq = repoSwitchRef.current;
    setIndexState("indexing");
    try {
      const idx =
        indexState === "no-data"
          ? await api.ciCreateIndex(token, activeRepoId, index?.branch ?? "main", true)
          : await api.ciRebuildIndex(token, activeRepoId);
      if (seq !== repoSwitchRef.current) return;
      setIndex(idx);
      setIndexState(idx.status === "ready" ? "ready" : "indexing");
    } catch (e) {
      if (seq !== repoSwitchRef.current) return;
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setIndexState(indexState === "no-data" ? "no-data" : "failed");
    }
  }, [activeRepoId, indexState, index]);

  const filteredRepos = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return repos;
    return repos.filter(
      ({ repository }) =>
        repository.name.toLowerCase().includes(q) || repository.full_name.toLowerCase().includes(q),
    );
  }, [repos, filter]);

  const selection = useMemo(
    () => ({
      file: fileDetail,
      fileLoading,
      fileError,
      searchHit: activeFileHit,
    }),
    [fileDetail, fileLoading, fileError, activeFileHit],
  );

  return (
    <div className="flex h-full min-h-0">
      {/* Left: repositories */}
      <aside className="hidden w-64 shrink-0 border-r border-outline bg-surface md:block" aria-label="Repositories">
        <RepositoryList
          repositories={filteredRepos}
          loading={reposLoading}
          error={reposError}
          activeId={activeRepoId}
          filter={filter}
          onFilterChange={setFilter}
          onSelect={(id) => void selectRepository(id)}
          onRetry={() => void loadRepositories()}
        />
      </aside>

      {/* Center: search + results + viewer */}
      <main className="flex min-h-0 min-w-0 flex-1 flex-col" aria-label="Code intelligence">
        <CodeSearchBar
          disabled={!activeRepoId}
          loading={searchLoading}
          onSearch={(q, sym) => void handleSearch(q, sym)}
        />
        {!activeRepoId ? (
          <EmptyRepositoriesHint />
        ) : (
          <>
            {activeRepo && (
              <div className="flex items-center gap-2 border-b border-outline-variant px-4 py-2">
                <span className="truncate font-mono text-xs font-bold text-on-surface">{activeRepo.name}</span>
                <span className="font-mono text-[10px] text-on-surface-variant">
                  {activeRepo.default_branch}
                </span>
                {indexState !== "ready" && (
                  <BrutalButton variant="ghost" size="sm" onClick={() => void rebuildIndex()}>
                    {indexState === "indexing" ? "Indexing…" : "Reindex"}
                  </BrutalButton>
                )}
              </div>
            )}
            <div className="flex-1 overflow-y-auto">
              {activeSymbol ? (
                <SymbolDetailPanel
                  symbol={symbolDetail}
                  loading={symbolLoading}
                  error={symbolError}
                  onRetry={() => (activeSymbol ? void selectSymbol(activeSymbol) : undefined)}
                  onDependencyClick={openSymbolById}
                />
              ) : (
                <CodeViewer
                  selection={selection}
                  repositoryName={activeRepo?.name}
                  defaultBranch={index?.branch ?? activeRepo?.default_branch}
                  onSymbolClick={(symbolId) => openSymbolById(symbolId)}
                  onRetry={() =>
                    activeFileHit ? void openResult(activeFileHit) : undefined
                  }
                />
              )}
            </div>
            <div className="max-h-64 overflow-y-auto">
              <SearchResults
                search={search}
                symbols={symbolResults}
                loading={searchLoading}
                error={searchError}
                activeFile={activeFileHit?.file_path ?? null}
                activeSymbol={activeSymbol?.id ?? null}
                onOpenResult={(hit) => void openResult(hit)}
                onSelectSymbol={(sym) => void selectSymbol(sym)}
                onRetry={() => void handleSearch(search?.query ?? "", false)}
              />
            </div>
            <DeveloperPanel
              key={activeRepoId}
              repoId={activeRepoId}
              defaultBranch={index?.branch ?? activeRepo?.default_branch}
            />
          </>
        )}
      </main>

      {/* Right: intelligence */}
      {activeRepoId ? (
        <aside className="hidden w-80 shrink-0 border-l border-outline bg-surface lg:block" aria-label="Intelligence">
          <IntelligencePanel key={activeRepoId} repoId={activeRepoId} />
        </aside>
      ) : null}
    </div>
  );
}

function EmptyRepositoriesHint() {
  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="border border-outline bg-surface p-8 text-center">
        <p className="font-bold text-on-surface">Code Intelligence</p>
        <p className="mt-2 text-sm text-on-surface-variant">
          Select a repository to search its indexed code, inspect symbols and references, and load impact,
          security, quality, test, ownership and history intelligence.
        </p>
      </div>
    </div>
  );
}