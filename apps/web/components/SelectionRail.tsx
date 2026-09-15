"use client";

import { CompanyRow } from "@/components/CompanyRow";
import type { Picked } from "@/components/CompanyRow";
import { StatusBadge } from "@/components/StatusBadge";
import { MAX_COMPANIES } from "@/lib/api";
import type { CompanyHit } from "@/lib/api";

export function SelectionRail({
  query,
  onQueryChange,
  onSearch,
  searching,
  hits,
  picked,
  onAdd,
  onRemove,
  onToggleFiling,
  question,
  onQuestionChange,
  onRun,
  busy,
  canRun,
  summary,
  disabled,
}: {
  query: string;
  onQueryChange: (value: string) => void;
  onSearch: () => void;
  searching: boolean;
  hits: CompanyHit[] | null;
  picked: Picked[];
  onAdd: (hit: CompanyHit) => void;
  onRemove: (companyNumber: string) => void;
  onToggleFiling: (companyNumber: string, transactionId: string) => void;
  question: string;
  onQuestionChange: (value: string) => void;
  onRun: () => void;
  busy: boolean;
  canRun: boolean;
  summary: string;
  disabled: boolean;
}) {
  const full = picked.length >= MAX_COMPANIES;

  return (
    <div className="flex h-full flex-col">
      {/* Search */}
      <div className="border-b border-line p-4">
        <label className="label" htmlFor="company-search">
          Add a company
        </label>
        <div className="mt-2 flex gap-2">
          <input
            id="company-search"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onSearch()}
            placeholder="Name or number"
            disabled={disabled}
            className="input min-w-0 flex-1"
          />
          <button
            type="button"
            onClick={onSearch}
            disabled={searching || !query.trim() || disabled}
            className="btn-primary shrink-0"
          >
            {searching ? "…" : "Search"}
          </button>
        </div>
        {full && (
          <p className="mt-2 text-xs text-muted">
            {MAX_COMPANIES} companies is the limit — remove one to add another.
          </p>
        )}

        {hits !== null && (
          <ul className="mt-3 max-h-64 overflow-y-auto rounded-md border border-line">
            {hits.length === 0 ? (
              <li className="px-3 py-2 text-xs text-muted">No companies matched.</li>
            ) : (
              hits.map((hit) => {
                const added = picked.some((p) => p.profile.company_number === hit.company_number);
                return (
                  <li
                    key={hit.company_number}
                    className="flex items-center gap-2 border-b border-line px-3 py-2 last:border-b-0"
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-xs font-medium text-ink" title={hit.title}>
                        {hit.title}
                      </span>
                      <span className="mt-0.5 flex items-center gap-1.5 text-xs text-muted">
                        <span className="num">{hit.company_number}</span>
                        <StatusBadge status={hit.company_status} />
                      </span>
                    </span>
                    <button
                      type="button"
                      onClick={() => onAdd(hit)}
                      disabled={added || full || disabled}
                      aria-label={`Add ${hit.title}`}
                      className="btn-secondary shrink-0 px-2 py-1 text-xs"
                    >
                      {added ? "Added" : "Add"}
                    </button>
                  </li>
                );
              })
            )}
          </ul>
        )}
      </div>

      {/* Selected companies */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <p className="label px-4 pt-4">
          Selected ({picked.length}/{MAX_COMPANIES})
        </p>
        {picked.length === 0 ? (
          <p className="px-4 py-3 text-xs text-muted">
            Search above, then pick which years of accounts you want for each company.
          </p>
        ) : (
          <ul className="mt-2">
            {picked.map((p) => (
              <CompanyRow
                key={p.profile.company_number}
                picked={p}
                onToggleFiling={onToggleFiling}
                onRemove={onRemove}
              />
            ))}
          </ul>
        )}
      </div>

      {/* Run */}
      <div className="space-y-2.5 border-t border-line p-4">
        <div>
          <label className="label" htmlFor="question">
            Question (optional)
          </label>
          <textarea
            id="question"
            value={question}
            onChange={(e) => onQuestionChange(e.target.value)}
            rows={2}
            placeholder="e.g. Which has the strongest balance sheet?"
            disabled={disabled}
            className="input mt-1.5 resize-y text-xs"
          />
        </div>
        <button
          type="button"
          onClick={onRun}
          disabled={!canRun || busy || disabled}
          className="btn-primary w-full"
        >
          {busy ? "Reviewing…" : "Review with Claude"}
        </button>
        <p className="text-xs text-subtle">{summary}</p>
      </div>
    </div>
  );
}
