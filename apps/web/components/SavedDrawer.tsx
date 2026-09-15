"use client";

import { useEffect, useState } from "react";
import { api, fmtWhen } from "@/lib/api";
import type { SavedItem } from "@/lib/api";

/** Everything ever analysed, kept until deleted. */
export function SavedDrawer({
  open,
  onClose,
  onOpenItem,
  reloadKey,
}: {
  open: boolean;
  onClose: () => void;
  onOpenItem: (item: SavedItem) => void;
  /** Bump to refetch — e.g. when a run finishes. */
  reloadKey: number;
}) {
  const [items, setItems] = useState<SavedItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    api
      .saved()
      .then(setItems)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [open, reloadKey]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  async function remove(item: SavedItem) {
    if (!confirm(`Delete "${item.title}" permanently?`)) return;
    setBusyId(item.id);
    try {
      if (item.kind === "analysis") await api.deleteAnalysis(item.id);
      else await api.deleteComparison(item.id);
      setItems((current) => (current ?? []).filter((i) => i.id !== item.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      <div
        className="fixed inset-0 z-30 bg-slate-900/20 backdrop-blur-[1px]"
        onClick={onClose}
        aria-hidden
      />
      <aside className="fixed right-0 top-0 z-40 flex h-full w-full max-w-sm flex-col border-l border-line bg-surface shadow-raised">
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <div>
            <h2 className="card-title">Saved</h2>
            <p className="mt-0.5 text-xs text-muted">
              Everything you have run, kept until you delete it.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close saved"
            className="rounded p-1 text-subtle hover:bg-canvas hover:text-ink"
          >
            <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
              <path d="M4 4l8 8M12 4l-8 8" />
            </svg>
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {error && <p className="px-4 py-3 text-sm text-red-600">{error}</p>}
          {items === null ? (
            <p className="px-4 py-3 text-sm text-muted">Loading…</p>
          ) : items.length === 0 ? (
            <p className="px-4 py-3 text-sm text-muted">
              Nothing saved yet. Every analysis and comparison you run is kept here.
            </p>
          ) : (
            <ul>
              {items.map((item) => (
                <li
                  key={item.id}
                  className="flex items-start gap-2 border-b border-line px-4 py-3 last:border-b-0"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-ink" title={item.title}>
                      {item.title}
                    </p>
                    <p className="mt-0.5 truncate text-xs text-muted" title={item.subtitle}>
                      {item.subtitle}
                    </p>
                    <p className="mt-1 flex items-center gap-1.5 text-xs text-subtle">
                      <span className={item.kind === "comparison" ? "badge-violet" : "badge-neutral"}>
                        {item.kind === "comparison" ? "comparison" : "company"}
                      </span>
                      {item.research && <span className="badge-neutral">web</span>}
                      {item.status === "error" && <span className="badge-amber">failed</span>}
                      <span className="num">{fmtWhen(item.created_at)}</span>
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-col gap-1">
                    <button
                      type="button"
                      onClick={() => onOpenItem(item)}
                      className="btn-secondary px-2 py-1 text-xs"
                    >
                      Open
                    </button>
                    <button
                      type="button"
                      onClick={() => remove(item)}
                      disabled={busyId === item.id}
                      className="rounded-md border border-line px-2 py-1 text-xs text-muted transition-colors hover:border-red-300 hover:bg-red-50 hover:text-red-600 disabled:opacity-50 dark:hover:border-red-900 dark:hover:bg-red-950/40"
                    >
                      Delete
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>
    </>
  );
}
