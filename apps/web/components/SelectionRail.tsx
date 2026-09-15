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
  onClearSearch,
  searching,
  hits,
  picked,
  onAdd,
  onRemove,
  onToggleFiling,
  onToggleTradingName,
  onTradingNameChange,
  research,
  onResearchChange,
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
  onClearSearch: () => void;
  searching: boolean;
  hits: CompanyHit[] | null;
  picked: Picked[];
  onAdd: (hit: CompanyHit) => void;
  onRemove: (companyNumber: string) => void;
  onToggleFiling: (companyNumber: string, transactionId: string) => void;
  onToggleTradingName: (companyNumber: string) => void;
  onTradingNameChange: (companyNumber: string, value: string) => void;
  research: boolean;
  onResearchChange: (value: boolean) => void;
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
          <div className="relative min-w-0 flex-1">
            <input
              id="company-search"
              value={query}
              onChange={(e) => onQueryChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") onSearch();
                if (e.key === "Escape") onClearSearch();
              }}
              placeholder="Name or number"
              disabled={disabled}
              className={`input ${query ? "pr-8" : ""}`}
            />
            {query && (
              <button
                type="button"
                onClick={onClearSearch}
                aria-label="Clear search"
                title="Clear search"
                className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-1 text-subtle hover:bg-canvas hover:text-ink"
              >
                <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
                  <path d="M4 4l8 8M12 4l-8 8" />
                </svg>
              </button>
            )}
          </div>
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
          <div className="mt-3 overflow-hidden rounded-md border border-line">
            <div className="flex items-center justify-between border-b border-line bg-canvas px-3 py-1.5">
              <span className="text-xs text-muted">
                {hits.length} {hits.length === 1 ? "result" : "results"}
              </span>
              <button type="button" onClick={onClearSearch} className="text-xs font-medium text-accent hover:underline">
                Clear
              </button>
            </div>
            <ul className="max-h-64 overflow-y-auto">
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
          </div>
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
                onToggleTradingName={onToggleTradingName}
                onTradingNameChange={onTradingNameChange}
                showTradingName={research}
              />
            ))}
          </ul>
        )}
      </div>

      {/* Run */}
      <div className="space-y-2.5 border-t border-line p-4">
        <label className="flex items-start gap-2 text-xs">
          <input
            type="checkbox"
            checked={research}
            onChange={(e) => onResearchChange(e.target.checked)}
            disabled={disabled}
            className="checkbox mt-0.5"
          />
          <span>
            <span className="font-medium text-ink">Research online</span>
            <span className="block text-muted">
              Revenue model and recent news, from the company&rsquo;s website and
              coverage. Slower, and costs more.
            </span>
          </span>
        </label>
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
