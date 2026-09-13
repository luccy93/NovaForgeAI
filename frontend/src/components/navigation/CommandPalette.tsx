"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { NAV_ITEMS, filterNavByPermission } from "@/lib/navigation";
import { api, clearToken, getToken } from "@/lib/api";
import { ApiError } from "@/lib/api-client";

const DEBOUNCE_MS = 250;

interface PaletteItem {
  id: string;
  label: string;
  hint: string;
  disabled?: boolean;
  run: () => void;
}

interface PaletteSection {
  id: string;
  label: string;
  items: Array<PaletteItem>;
}

interface SearchHit {
  id: string;
  label: string;
  snippet: string;
}

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const [searching, setSearching] = useState(false);
  const [hits, setHits] = useState<Array<SearchHit>>([]);
  const [permissions, setPermissions] = useState<string[] | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const timerRef = useRef<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const seqRef = useRef(0);

  useEffect(() => {
    if (open) {
      const timer = setTimeout(() => inputRef.current?.focus(), 30);
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [open]);

  // Refetch the permission signal on open so navigation gating stays current.
  useEffect(() => {
    if (!open) return;
    const token = getToken();
    if (!token) return;
    api
      .whoami(token)
      .then((who) => setPermissions(who.permissions ?? []))
      .catch(() => undefined);
  }, [open]);

  // Abort any in-flight search and drop results on tenant/workspace switch to
  // prevent cross-tenant leakage.
  useEffect(() => {
    function onSwitch() {
      abortRef.current?.abort();
      setHits([]);
      setSearching(false);
    }
    window.addEventListener("tenant:switched", onSwitch);
    window.addEventListener("workspace:switched", onSwitch);
    return () => {
      window.removeEventListener("tenant:switched", onSwitch);
      window.removeEventListener("workspace:switched", onSwitch);
    };
  }, []);

  useEffect(() => () => {
    if (timerRef.current !== null) clearTimeout(timerRef.current);
    abortRef.current?.abort();
  }, []);

  function close() {
    if (timerRef.current !== null) clearTimeout(timerRef.current);
    abortRef.current?.abort();
    setQuery("");
    setHits([]);
    setSearching(false);
    setActiveIndex(0);
    onClose();
  }

  function onQueryChange(value: string) {
    setQuery(value);
    setActiveIndex(0);
    if (timerRef.current !== null) clearTimeout(timerRef.current);
    const snapshot = value.trim();
    if (snapshot.length < 2) {
      abortRef.current?.abort();
      setHits([]);
      setSearching(false);
      return;
    }
    const token = getToken();
    if (!token) {
      setHits([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    const seq = ++seqRef.current;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    timerRef.current = window.setTimeout(() => {
      void Promise.all([
        api.knowledgeSearch(token, snapshot, { limit: 5, signal: controller.signal }),
        api.dataCatalogSearch(token, snapshot, { limit: 5 }),
      ])
        .then(([knowledge, catalog]) => {
          if (seq !== seqRef.current) return;
          const next: Array<SearchHit> = [];
          for (const item of knowledge.items ?? []) {
            next.push({
              id: `hit-${next.length}`,
              label: String(item.title ?? item.document_id ?? "Knowledge result"),
              snippet: String(item.snippet ?? "").slice(0, 120),
            });
          }
          for (const item of catalog.items ?? []) {
            next.push({
              id: `hit-${next.length}`,
              label: String(item.name ?? item.id ?? "Catalog result"),
              snippet: [item.description, item.owner, item.classification]
                .filter(Boolean)
                .join(" · ")
                .slice(0, 120) || "Data catalog result",
            });
          }
          setHits(next);
        })
        .catch((e) => {
          if (seq !== seqRef.current) return;
          if (e instanceof ApiError && e.kind === "unauthorized") {
            clearToken();
            window.location.href = "/auth/login";
            return;
          }
          setHits([]);
        })
        .finally(() => {
          if (seq === seqRef.current) setSearching(false);
        });
    }, DEBOUNCE_MS);
  }

  const sections: Array<PaletteSection> = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filterMatches = (value: string) => q === "" || value.toLowerCase().includes(q);

    const navigation: Array<PaletteItem> = filterNavByPermission(
      NAV_ITEMS.filter(
        (item) =>
          q === "" ||
          item.label.toLowerCase().includes(q) ||
          item.id.includes(q) ||
          item.description.toLowerCase().includes(q),
      ),
      permissions,
    ).map((item) => ({
      id: `nav-${item.id}`,
      label: `Go to ${item.label}`,
      hint: item.description,
      run: () => {
        window.location.href = item.href;
      },
    }));

    const searchCandidates = [
      { id: "search-everything", label: "Search everything", hint: "Universal search surface", href: "/knowledge/universal" },
      { id: "search-knowledge", label: "Search Knowledge", hint: "Knowledge base workspace", href: "/knowledge" },
      { id: "search-code", label: "Search Code", hint: "Code intelligence workspace", href: "/code" },
    ].filter((item) => q === "" || filterMatches(item.label));
    const search: Array<PaletteItem> = searchCandidates.map((item) => ({
      id: item.id,
      label: item.label,
      hint: item.hint,
      run: () => {
        window.location.href = item.href;
      },
    }));

    const recent: Array<PaletteItem> =
      q === ""
        ? [
            {
              id: "recent-empty",
              label: "No recent resources exposed by API.",
              hint: "Recent activity has no safe IAM-scoped contract, so nothing is fabricated here.",
              disabled: true,
              run: () => {},
            },
          ]
        : [];

    const helpCandidates = [
      { id: "help-ai", label: "Ask AI", hint: "Open the AI workspace", href: "/ai" },
    ].filter((item) => q === "" || filterMatches(item.label));
    const help: Array<PaletteItem> = helpCandidates.map((item) => ({
      id: item.id,
      label: item.label,
      hint: item.hint,
      run: () => {
        window.location.href = item.href;
      },
    }));

    const results: Array<PaletteItem> = hits.map((hit) => ({
      id: hit.id,
      label: hit.label,
      hint: hit.snippet,
      disabled: true,
      run: () => {},
    }));

    const sectionsOut: Array<PaletteSection> = [];
    if (navigation.length > 0 || q === "") {
      sectionsOut.push({ id: "navigation", label: "Navigation", items: navigation });
    }
    if (search.length > 0 || results.length > 0 || searching) {
      sectionsOut.push({ id: "search", label: "Search", items: [...search, ...results] });
    }
    if (recent.length > 0) {
      sectionsOut.push({ id: "recent", label: "Recent", items: recent });
    }
    if (help.length > 0) {
      sectionsOut.push({ id: "help", label: "Help", items: help });
    }
    return sectionsOut;
  }, [query, hits, searching, permissions]);

  const interactive = useMemo(() => sections.flatMap((s) => s.items).filter((item) => !item.disabled), [sections]);
  const activeIndexSafe = interactive.length === 0 ? 0 : Math.min(activeIndex, interactive.length - 1);
  const activeItem = interactive[activeIndexSafe] ?? null;

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      close();
      return;
    }
    if (interactive.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((activeIndexSafe + 1) % interactive.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((activeIndexSafe - 1 + interactive.length) % interactive.length);
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (activeItem) {
        close();
        activeItem.run();
      }
    }
  }

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          className="fixed inset-0 z-[80] bg-black/70 p-4 pt-24"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.12 }}
          onClick={close}
          role="presentation"
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label="Command palette"
            className="mx-auto max-w-xl border border-outline bg-surface-container"
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.12 }}
            onClick={(event) => event.stopPropagation()}
          >
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => onQueryChange(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Type a command or search…"
              aria-label="Command palette query"
              aria-controls="command-palette-results"
              className="w-full border-b border-outline bg-transparent px-4 py-3 text-body-md text-on-surface placeholder:text-on-surface-variant/50 outline-none"
            />
            <ul
              id="command-palette-results"
              className="max-h-80 overflow-y-auto p-2"
              role="listbox"
              aria-label="Results"
              aria-activedescendant={activeItem?.id}
            >
              {sections.map((section) => (
                <li key={section.id} aria-label={section.label} role="presentation">
                  <p className="px-3 pb-1 pt-2 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                    {section.label}
                  </p>
                  <ul role="presentation">
                    {section.items.map((item) => (
                      <li key={`${section.id}-${item.id}`}>
                        <button
                          id={item.id}
                          type="button"
                          role="option"
                          aria-selected={activeItem?.id === item.id}
                          disabled={item.disabled}
                          onMouseEnter={() => {
                            const index = interactive.findIndex((candidate) => candidate.id === item.id);
                            if (index >= 0) setActiveIndex(index);
                          }}
                          onClick={() => {
                            if (item.disabled) return;
                            close();
                            item.run();
                          }}
                          className={`block w-full px-3 py-2 text-left ${
                            item.disabled
                              ? "cursor-default text-on-surface-variant"
                              : item.id === activeItem?.id
                                ? "bg-surface-container-high text-on-surface"
                                : "text-on-surface hover:bg-surface-container-high"
                          }`}
                        >
                          <p className={`text-sm font-bold ${item.disabled ? "font-normal" : ""}`}>{item.label}</p>
                          <p className="text-xs text-on-surface-variant">{item.hint}</p>
                        </button>
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
              {searching ? (
                <li className="px-3 py-2 font-mono text-xs text-on-surface-variant" role="presentation">
                  Searching…
                </li>
              ) : null}
              {sections.length === 0 ? (
                <li className="px-3 py-2 text-sm text-on-surface-variant" role="presentation">
                  No matches.
                </li>
              ) : null}
            </ul>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}