import { useCallback } from "react";

interface TablistItem<TId extends string = string> {
  id: TId;
  label: string;
}

export function useTablistKeyboard<TId extends string>({
  tabs,
  activeId,
  setActiveId,
  idPrefix,
}: {
  tabs: TablistItem<TId>[];
  activeId: TId;
  setActiveId: (id: TId) => void;
  idPrefix: string;
}) {
  const tabId = (id: TId) => `${idPrefix}-tab-${id}`;
  const panelId = (id: TId) => `${idPrefix}-panel-${id}`;

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLElement>) => {
      const idx = tabs.findIndex((t) => t.id === activeId);
      if (idx === -1) return;
      let nextId: TId | undefined;
      if (e.key === "ArrowRight") {
        nextId = tabs[(idx + 1) % tabs.length].id;
      } else if (e.key === "ArrowLeft") {
        nextId = tabs[(idx - 1 + tabs.length) % tabs.length].id;
      } else if (e.key === "Home") {
        nextId = tabs[0].id;
      } else if (e.key === "End") {
        nextId = tabs[tabs.length - 1].id;
      }
      if (!nextId || nextId === activeId) return;
      e.preventDefault();
      setActiveId(nextId);
      document.getElementById(`${idPrefix}-tab-${nextId}`)?.focus();
    },
    [tabs, activeId, setActiveId, idPrefix],
  );

  return {
    onKeyDown,
    tabProps: (id: TId) => ({
      id: tabId(id),
      "aria-controls": panelId(id),
      tabIndex: id === activeId ? 0 : -1,
    }),
    panelProps: (id: TId) => ({
      id: panelId(id),
      role: "tabpanel" as const,
      "aria-labelledby": tabId(id),
    }),
  };
}