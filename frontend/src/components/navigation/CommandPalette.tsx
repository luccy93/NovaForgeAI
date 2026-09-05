"use client";

import { useEffect, useMemo, useRef, useState } from "react";

const DEBOUNCE_MS = 300;
import { AnimatePresence, motion } from "framer-motion";
import { NAV_ITEMS } from "@/lib/navigation";
import { api, getToken } from "@/lib/api";

interface PaletteResult {
  id: string;
  title: string;
  hint: string;
  run: () => void;
}

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Array<{ title: string; snippet: string }>>([]);
  const [searching, setSearching] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const timerRef = useRef<number | null>(null);
  const token = typeof window === "undefined" ? null : getToken();

  useEffect(() => {
    if (open) {
      const timer = setTimeout(() => inputRef.current?.focus(), 30);
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [open ]);

  useEffect(() => () => {
    if (timerRef.current !== null) clearTimeout(timerRef.current);
  }, []);

  function close() {
    if (timerRef.current !== null) clearTimeout(timerRef.current);
    setQuery("");
    setHits([]);
    setSearching(false);
    onClose();
  }

  function onQueryChange(value: string) {
    setQuery(value);
    if (timerRef.current !== null) clearTimeout(timerRef.current);
    if (value.trim().length < 2 || !token) {
      setHits([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    const snapshot = value.trim();
    timerRef.current = window.setTimeout(() => {
      api
        .knowledgeSearch(token, snapshot, 5)
        .then((res) =>
          setHits(
            (res.items ?? []).map((item) => ({
              title: String(item.title ?? item.document_id ?? "Result"),
              snippet: String(item.snippet ?? "").slice(0, 120),
            })),
          ),
        )
        .catch(() => setHits([]))
        .finally(() => setSearching(false));
    }, DEBOUNCE_MS);
  }

  const actions: Array<PaletteResult> = useMemo(() => {
    const q = query.trim().toLowerCase();
    return NAV_ITEMS.filter(
      (item) => q === "" || item.label.toLowerCase().includes(q) || item.id.includes(q),
    ).map((item) => ({
      id: `nav-${item.id}`,
      title: `Go to ${item.label}`,
      hint: item.description,
      run: () => {
        window.location.href = item.href;
      },
    }));
  }, [query]);

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
              onKeyDown={(e) => {
                if (e.key === "Escape") close();
              }}
              placeholder="Type a command or search knowledge…"
              aria-label="Command palette query"
              className="w-full border-b border-outline bg-transparent px-4 py-3 text-body-md text-on-surface placeholder:text-on-surface-variant/50 outline-none"
            />
            <ul className="max-h-80 overflow-y-auto p-2" role="listbox" aria-label="Results">
              {actions.map((action) => (
                <li key={action.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected="false"
                    onClick={() => {
                      close();
                      action.run();
                    }}
                    className="block w-full px-3 py-2 text-left hover:bg-surface-container-high"
                  >
                    <p className="text-sm font-bold text-on-surface">{action.title}</p>
                    <p className="text-xs text-on-surface-variant">{action.hint}</p>
                  </button>
                </li>
              ))}
              {searching ? (
                <li className="px-3 py-2 font-mono text-xs text-on-surface-variant">Searching…</li>
              ) : (
                hits.map((hit, index) => (
                  <li key={`hit-${index}`} className="px-3 py-2">
                    <p className="text-sm font-bold text-primary-container">{hit.title}</p>
                    <p className="text-xs text-on-surface-variant">{hit.snippet}</p>
                  </li>
                ))
              )}
              {actions.length === 0 && !searching && hits.length === 0 ? (
                <li className="px-3 py-2 text-sm text-on-surface-variant">No matches.</li>
              ) : null}
            </ul>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
