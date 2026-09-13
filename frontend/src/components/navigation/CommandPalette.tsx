"use client";

/* eslint-disable react-hooks/set-state-in-effect -- authoritative permission/action load from the backend on open is intentional */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { NAV_ITEMS, filterNavByPermission } from "@/lib/navigation";
import { api, clearToken, getToken } from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import { hasPermission } from "@/lib/permissions";
import { useAuthStore } from "@/stores/auth";
import { useToastStore } from "@/stores/toast";
import { PERMISSIONS } from "@/types/auth";
import type { AccessRequestItem } from "@/types/security";
import type { ZeroTrustReview } from "@/types/admin";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalModal } from "@/components/ui/BrutalModal";

const DEBOUNCE_MS = 250;
const LOGIN_PATH = "/auth/login";

interface PaletteItem {
  id: string;
  label: string;
  hint: string;
  disabled?: boolean;
  keepOpen?: boolean;
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
  const rootRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const seqRef = useRef(0);
  const actionSeqRef = useRef(0);
  const pushToast = useToastStore((s) => s.push);
  const [actionTargets, setActionTargets] = useState<{ requests: AccessRequestItem[]; reviews: ZeroTrustReview[] }>({
    requests: [],
    reviews: [],
  });
  const [pendingAction, setPendingAction] = useState<
    | { kind: "approve-request"; id: string; label: string }
    | { kind: "certify-review"; id: string; label: string }
    | null
  >(null);
  const [confirming, setConfirming] = useState(false);
  const [certifyChecked, setCertifyChecked] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      const timer = setTimeout(() => inputRef.current?.focus(), 30);
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [open]);

  const authExpired = useCallback(() => {
    useAuthStore.getState().markExpired();
    window.location.href = LOGIN_PATH;
  }, []);

  // Refetch the permission signal and actionable Zero Trust targets on open so
  // navigation gating and ACTION items stay current.
  const loadActionTargets = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    const seq = ++actionSeqRef.current;
    try {
      const [requests, reviews] = await Promise.all([
        api.zeroTrustAccessRequests(token, { limit: 10, status: "REQUESTED" }),
        api.zeroTrustReviews(token, { limit: 10, status: "pending" }),
      ]);
      if (seq !== actionSeqRef.current) return;
      setActionTargets({
        requests: Array.isArray(requests.items) ? requests.items : [],
        reviews: Array.isArray(reviews.items) ? reviews.items : [],
      });
    } catch (e) {
      if (seq !== actionSeqRef.current) return;
      if (e instanceof ApiError && e.kind === "unauthorized") {
        authExpired();
        return;
      }
      setActionTargets({ requests: [], reviews: [] });
    }
  }, [authExpired]);

  useEffect(() => {
    if (!open) return;
    const token = getToken();
    if (!token) return;
    api
      .whoami(token)
      .then((who) => setPermissions(who.permissions ?? []))
      .catch(() => undefined);
    void loadActionTargets();
  }, [open, loadActionTargets]);

  // Abort any in-flight search and drop results on tenant/workspace switch to
  // prevent cross-tenant leakage.
  useEffect(() => {
    function onSwitch() {
      abortRef.current?.abort();
      actionSeqRef.current += 1;
      setHits([]);
      setSearching(false);
      setActionTargets({ requests: [], reviews: [] });
      setPendingAction(null);
      setCertifyChecked(false);
      setActionError(null);
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
    actionSeqRef.current += 1;
    setQuery("");
    setHits([]);
    setSearching(false);
    setActiveIndex(0);
    setActionTargets({ requests: [], reviews: [] });
    setPendingAction(null);
    setCertifyChecked(false);
    setActionError(null);
    onClose();
  }

  async function runPendingAction() {
    if (!pendingAction) return;
    if (pendingAction.kind === "certify-review" && !certifyChecked) return;
    const token = getToken();
    if (!token) {
      authExpired();
      return;
    }
    setConfirming(true);
    setActionError(null);
    try {
      if (pendingAction.kind === "approve-request") {
        await api.zeroTrustApproveAccessRequest(token, pendingAction.id);
        pushToast("success", "Access request approved and activated");
      } else {
        await api.zeroTrustCertifyReview(token, pendingAction.id);
        pushToast("success", "Access review certified");
      }
      setPendingAction(null);
      setCertifyChecked(false);
      await loadActionTargets();
    } catch (e) {
      if (e instanceof ApiError && (e.status === 404 || e.status === 409)) {
        setPendingAction(null);
        setCertifyChecked(false);
        pushToast("warning", "Target is no longer actionable — the list was refreshed from the backend.");
        await loadActionTargets();
        return;
      }
      if (e instanceof ApiError && e.kind === "unauthorized") {
        authExpired();
        return;
      }
      if (e instanceof ApiError && e.kind === "forbidden") {
        setActionError("Backend denied this action: zero_trust:write authorization is required.");
        return;
      }
      setActionError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setConfirming(false);
    }
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

    const actionsEnabled = hasPermission(permissions ?? [], PERMISSIONS.zeroTrustWrite);
    const actions: Array<PaletteItem> = [];
    if (actionsEnabled) {
      for (const row of actionTargets.requests) {
        if ((row.status ?? "") !== "REQUESTED") continue;
        const label = `${row.identity ?? row.id} · ${row.action ?? "access"}`;
        if (q !== "" && !label.toLowerCase().includes(q)) continue;
        actions.push({
          id: `approve-${row.id}`,
          label: `Approve access request: ${label}`,
          hint: "Explicit backend approval",
          keepOpen: true,
          run: () => {
            setActionError(null);
            setCertifyChecked(false);
            setPendingAction({ kind: "approve-request", id: row.id, label });
          },
        });
      }
      for (const row of actionTargets.reviews) {
        if ((row.status ?? "") !== "pending") continue;
        const label = `${row.review_type ?? "review"} · ${row.scope ?? "all"}`;
        if (q !== "" && !label.toLowerCase().includes(q)) continue;
        actions.push({
          id: `certify-${row.id}`,
          label: `Certify access review: ${label}`,
          hint: "Explicit backend certification",
          keepOpen: true,
          run: () => {
            setActionError(null);
            setCertifyChecked(false);
            setPendingAction({ kind: "certify-review", id: row.id, label });
          },
        });
      }
    }

    const sectionsOut: Array<PaletteSection> = [];
    if (navigation.length > 0 || q === "") {
      sectionsOut.push({ id: "navigation", label: "Navigation", items: navigation });
    }
    if (actions.length > 0) {
      sectionsOut.push({ id: "actions", label: "Actions", items: actions });
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
  }, [query, hits, searching, permissions, actionTargets]);

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
        if (activeItem.keepOpen) {
          activeItem.run();
        } else {
          close();
          activeItem.run();
        }
      }
    }
  }

  function onDialogKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "Tab") return;
    const root = rootRef.current;
    if (!root) return;
    const focusables = Array.from(root.querySelectorAll<HTMLElement>("input, button:not([disabled])"));
    if (focusables.length === 0) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <>
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
              ref={rootRef}
              role="dialog"
              aria-modal="true"
              aria-label="Command palette"
              className="mx-auto max-w-xl border border-outline bg-surface-container"
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.12 }}
              onClick={(event) => event.stopPropagation()}
              onKeyDown={onDialogKeyDown}
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
                            if (item.keepOpen) {
                              item.run();
                            } else {
                              close();
                              item.run();
                            }
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
      <div className={pendingAction ? "fixed inset-0 z-[90]" : ""}>
        <BrutalModal
          open={pendingAction !== null}
          title={pendingAction?.kind === "certify-review" ? "Certify access review" : "Approve access request"}
          onClose={() => {
            if (!confirming) {
              setPendingAction(null);
              setActionError(null);
            }
          }}
          actions={
            <>
              <BrutalButton variant="ghost" size="sm" onClick={() => setPendingAction(null)} disabled={confirming}>
                Cancel
              </BrutalButton>
              <BrutalButton
                variant="primary"
                size="sm"
                onClick={() => void runPendingAction()}
                disabled={confirming || (pendingAction?.kind === "certify-review" && !certifyChecked)}
              >
                {pendingAction?.kind === "certify-review" ? "Confirm certification" : "Confirm approval"}
              </BrutalButton>
            </>
          }
        >
          {pendingAction ? (
            <div className="space-y-4 text-sm">
              <p>
                {pendingAction.kind === "certify-review"
                  ? "Certifying applies the backend certification flow for this access review."
                  : "Approving activates the requested privileged access in the backend."}
                <span className="font-mono text-xs"> {pendingAction.label}</span>
              </p>
              <p className="text-xs text-on-surface-variant">
                Authorization is enforced server-side using zero_trust:write.
              </p>
              {pendingAction.kind === "certify-review" ? (
                <label className="flex items-start gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={certifyChecked}
                    onChange={(e) => setCertifyChecked(e.target.checked)}
                    className="mt-1"
                  />
                  <span>I confirm this access review, representing an explicit certify approval.</span>
                </label>
              ) : null}
              {actionError ? <p className="font-bold text-error">{actionError}</p> : null}
            </div>
          ) : null}
        </BrutalModal>
      </div>
    </>
  );
}