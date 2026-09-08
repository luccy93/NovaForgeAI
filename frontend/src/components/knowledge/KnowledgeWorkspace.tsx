"use client";

/* eslint-disable react-hooks/set-state-in-effect -- must clear stale tenant/workspace data synchronously on context switch */

import { useCallback, useEffect, useRef, useState } from "react";
import { KnowledgeFilters } from "@/components/knowledge/KnowledgeFilters";
import { KnowledgeResultDetail } from "@/components/knowledge/KnowledgeResultDetail";
import { KnowledgeResults } from "@/components/knowledge/KnowledgeResults";
import { KnowledgeSearchBar } from "@/components/knowledge/KnowledgeSearchBar";
import { KnowledgeSourcesPanel } from "@/components/knowledge/KnowledgeSourcesPanel";
import { api, clearToken, getToken } from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import type {
  KnowledgeDocument,
  KnowledgeFreshnessStats,
  KnowledgeSearchFilterState,
  KnowledgeSearchItem,
  KnowledgeSearchResponse,
  KnowledgeSource,
  KnowledgeUsageStats,
} from "@/types/knowledge";

const PAGE_SIZE = 20;

function sessionExpired() {
  clearToken();
  window.location.href = "/auth/login";
}

interface SearchState {
  query: string;
  page: number;
  filters: KnowledgeSearchFilterState;
}

function parseUrl(): { state: SearchState; documentId: string | null } {
  if (typeof window === "undefined") {
    return { state: { query: "", page: 1, filters: {} }, documentId: null };
  }
  const docMatch = window.location.pathname.match(/^\/knowledge\/document\/([^/]+)$/);
  const params = new URLSearchParams(window.location.search);
  const n = Number.parseInt(params.get("page") ?? "", 10);
  return {
    state: {
      query: params.get("q") ?? "",
      page: Number.isFinite(n) && n >= 1 ? n : 1,
      filters: {
        source_type: params.get("st") ?? undefined,
        doc_type: params.get("dt") ?? undefined,
        classification: params.get("cl") ?? undefined,
      },
    },
    documentId: docMatch ? decodeURIComponent(docMatch[1]) : null,
  };
}

function buildSearchUrl(state: SearchState): string {
  const params = new URLSearchParams();
  if (state.query) params.set("q", state.query);
  if (state.page > 1) params.set("page", String(state.page));
  if (state.filters.source_type) params.set("st", state.filters.source_type);
  if (state.filters.doc_type) params.set("dt", state.filters.doc_type);
  if (state.filters.classification) params.set("cl", state.filters.classification);
  const qs = params.toString();
  return `/knowledge${qs ? `?${qs}` : ""}`;
}

export function KnowledgeWorkspace() {
  const [searchState, setSearchState] = useState<SearchState>({ query: "", page: 1, filters: {} });
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [selectedHit, setSelectedHit] = useState<KnowledgeSearchItem | null>(null);

  const [results, setResults] = useState<KnowledgeSearchResponse | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const [document, setDocument] = useState<KnowledgeDocument | null>(null);
  const [documentLoading, setDocumentLoading] = useState(false);
  const [documentError, setDocumentError] = useState<string | null>(null);

  const [sources, setSources] = useState<KnowledgeSource[] | null>(null);
  const [sourcesLoading, setSourcesLoading] = useState(true);
  const [sourcesError, setSourcesError] = useState<string | null>(null);
  const [freshness, setFreshness] = useState<KnowledgeFreshnessStats | null>(null);
  const [usage, setUsage] = useState<KnowledgeUsageStats | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const seqRef = useRef(0);

  const loadSidebar = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    const seq = seqRef.current;
    setSourcesLoading(true);
    setSourcesError(null);
    try {
      const [srcRes, freshnessRes, usageRes] = await Promise.all([
        api.knowledgeListSources(token, { limit: 100 }),
        api.knowledgeFreshnessStats(token).catch(() => null),
        api.knowledgeUsageStats(token, { since_hours: 24 }).catch(() => null),
      ]);
      if (seq !== seqRef.current) return;
      setSources((srcRes as { items: KnowledgeSource[] }).items ?? null);
      setFreshness(freshnessRes);
      setUsage(usageRes);
    } catch (e) {
      if (seq !== seqRef.current) return;
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setSourcesError(e instanceof Error ? e.message : "Failed to load sources");
    } finally {
      if (seq === seqRef.current) setSourcesLoading(false);
    }
  }, []);

  const runSearch = useCallback(async (state: SearchState) => {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    const q = state.query.trim();
    if (!q) {
      setResults(null);
      setSearchError(null);
      setSearchLoading(false);
      return;
    }
    seqRef.current += 1;
    const seq = seqRef.current;
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setSearchLoading(true);
    setSearchError(null);
    try {
      const res = await api.knowledgeSearch(
        token,
        q,
        {
          source_type: state.filters.source_type,
          doc_type: state.filters.doc_type,
          classification: state.filters.classification,
          limit: PAGE_SIZE,
          offset: (state.page - 1) * PAGE_SIZE,
          signal: controller.signal,
        },
      );
      if (seq !== seqRef.current) return;
      setResults(res);
    } catch (e) {
      if (seq !== seqRef.current || controller.signal.aborted) return;
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setSearchError(e instanceof Error ? e.message : "Search failed");
    } finally {
      if (seq === seqRef.current) setSearchLoading(false);
    }
  }, []);

  const loadDocument = useCallback(async (documentId: string, hit: KnowledgeSearchItem | null) => {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    seqRef.current += 1;
    const seq = seqRef.current;
    if (abortRef.current) abortRef.current.abort();
    setSelectedHit(hit);
    setSelectedDocId(documentId);
    setDocument(null);
    setDocumentError(null);
    setDocumentLoading(true);
    try {
      const detail = await api.knowledgeGetDocument(token, documentId);
      if (seq !== seqRef.current) return;
      setDocument(detail);
    } catch (e) {
      if (seq !== seqRef.current) return;
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setDocumentError(e instanceof Error ? e.message : "Document unavailable");
    } finally {
      if (seq === seqRef.current) setDocumentLoading(false);
    }
  }, []);

  const syncFromLocation = useCallback(() => {
    const { state, documentId } = parseUrl();
    setSearchState(state);
    if (documentId) {
      loadDocument(documentId, null);
    } else {
      setSelectedDocId(null);
      setSelectedHit(null);
      setDocument(null);
      setDocumentError(null);
      if (state.query.trim()) {
        void runSearch(state);
      } else {
        setResults(null);
      }
    }
  }, [loadDocument, runSearch]);

  useEffect(() => {
    void loadSidebar();
    const { documentId } = parseUrl();
    if (documentId) {
      void loadDocument(documentId, null);
    } else if (parseUrl().state.query.trim()) {
      void runSearch(parseUrl().state);
    }

    const onPopState = () => syncFromLocation();
    window.addEventListener("popstate", onPopState);

    const resetForContextSwitch = () => {
      seqRef.current += 1;
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
      setResults(null);
      setSearchLoading(false);
      setSearchError(null);
      setDocument(null);
      setDocumentError(null);
      setDocumentLoading(false);
      setSelectedDocId(null);
      setSelectedHit(null);
      setSources(null);
      setFreshness(null);
      setUsage(null);
      const blank = { query: "", page: 1, filters: {} };
      setSearchState(blank);
      if (typeof window !== "undefined") {
        window.history.replaceState(null, "", "/knowledge");
      }
      void loadSidebar();
    };
    window.addEventListener("tenant:switched", resetForContextSwitch as EventListener);
    window.addEventListener("workspace:switched", resetForContextSwitch as EventListener);

    return () => {
      window.removeEventListener("popstate", onPopState);
      window.removeEventListener("tenant:switched", resetForContextSwitch as EventListener);
      window.removeEventListener("workspace:switched", resetForContextSwitch as EventListener);
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
    };
  }, [loadDocument, loadSidebar, runSearch, syncFromLocation]);

  const commitSearchState = useCallback((next: SearchState, syncUrl: boolean) => {
    setSearchState(next);
    if (syncUrl && typeof window !== "undefined" && !selectedDocId) {
      window.history.replaceState(null, "", buildSearchUrl(next));
    }
  }, [selectedDocId]);

  const handleSearch = useCallback(
    (query: string) => {
      const next = { query: query.trim(), page: 1, filters: searchState.filters };
      commitSearchState(next, true);
      void runSearch(next);
      setSelectedDocId(null);
      setSelectedHit(null);
      setDocument(null);
    },
    [commitSearchState, runSearch, searchState.filters],
  );

  const handleFilterPatch = useCallback(
    (patch: Partial<KnowledgeSearchFilterState>) => {
      setSelectedDocId(null);
      setSelectedHit(null);
      setDocument(null);
      const next = {
        ...searchState,
        page: 1,
        filters: { ...searchState.filters, ...patch },
      };
      commitSearchState(next, true);
      if (next.query.trim()) void runSearch(next);
    },
    [commitSearchState, runSearch, searchState],
  );

  const handleClearFilters = useCallback(() => {
    setSelectedDocId(null);
    setSelectedHit(null);
    setDocument(null);
    const next = { ...searchState, page: 1, filters: {} };
    commitSearchState(next, true);
    if (next.query.trim()) void runSearch(next);
  }, [commitSearchState, runSearch, searchState]);

  const handlePageChange = useCallback(
    (page: number) => {
      setSelectedDocId(null);
      setSelectedHit(null);
      setDocument(null);
      const next = { ...searchState, page };
      commitSearchState(next, true);
      void runSearch(next);
    },
    [commitSearchState, runSearch, searchState],
  );

  const handleOpenResult = useCallback(
    (hit: KnowledgeSearchItem) => {
      const documentId = hit.document_id;
      if (!documentId) return;
      if (typeof window !== "undefined") {
        window.history.pushState(null, "", `/knowledge/document/${encodeURIComponent(documentId)}`);
      }
      void loadDocument(documentId, hit);
    },
    [loadDocument],
  );

  const handleBack = useCallback(() => {
    // The document view preserved the search state in memory (search URLs are
    // stored in history entries). Restore it deterministically instead of
    // relying on history.back()/popstate so the browser-back path keeps parity.
    const restored = searchState;
    setSearchState(restored);
    setSelectedDocId(null);
    setSelectedHit(null);
    setDocument(null);
    setDocumentError(null);
    if (restored.query.trim()) void runSearch(restored);
    else setResults(null);
    if (typeof window !== "undefined") {
      window.history.replaceState(null, "", buildSearchUrl(restored));
    }
  }, [runSearch, searchState]);

  const retryDocument = useCallback(() => {
    if (selectedDocId) void loadDocument(selectedDocId, selectedHit);
  }, [loadDocument, selectedDocId, selectedHit]);

  const isLockedSearchBar = selectedDocId !== null;

  return (
    <div className="flex h-full min-h-0">
      {/* Left: sources + platform status */}
      <aside className="hidden w-72 shrink-0 border-r border-outline bg-surface md:block" aria-label="Knowledge sources">
        <KnowledgeSourcesPanel
          sources={sources}
          sourcesLoading={sourcesLoading}
          sourcesError={sourcesError}
          freshness={freshness}
          usage={usage}
          onRetry={() => void loadSidebar()}
        />
      </aside>

      {/* Center: search + filters + results / detail */}
      <main className="flex min-h-0 min-w-0 flex-1 flex-col" aria-label="Knowledge workspace">
        {isLockedSearchBar ? null : (
          <>
            <KnowledgeSearchBar
              initialQuery={searchState.query}
              loading={searchLoading}
              onSearch={handleSearch}
            />
            <KnowledgeFilters
              filters={searchState.filters}
              disabled={searchLoading}
              onChange={handleFilterPatch}
              onClear={handleClearFilters}
            />
          </>
        )}
        <div className="min-h-0 flex-1 overflow-y-auto">
          {selectedDocId ? (
            <KnowledgeResultDetail
              hit={
                selectedHit ?? {
                  document_id: selectedDocId,
                  score: 0,
                  citations: [],
                }
              }
              document={document}
              loading={documentLoading}
              error={documentError}
              onBack={handleBack}
              onRetry={retryDocument}
            />
          ) : (
            <KnowledgeResults
              results={results}
              loading={searchLoading}
              error={searchError}
              query={searchState.query}
              selectedItem={selectedDocId}
              page={searchState.page}
              pageSize={PAGE_SIZE}
              onOpen={handleOpenResult}
              onRetry={() => void runSearch(searchState)}
              onPageChange={handlePageChange}
            />
          )}
        </div>
      </main>
    </div>
  );
}