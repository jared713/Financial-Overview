"use client";

import { useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import { YearPills } from "@/components/YearPills";
import { MAX_FILINGS_PER_COMPANY, estimateCost, filingPdfUrl } from "@/lib/api";
import type { CompanyAnalysis, CompanyProfile, Filing } from "@/lib/api";

export type Picked = {
  profile: CompanyProfile;
  filings: Filing[];
  selected: string[];
  loading: boolean;
  error?: string;
  tradingNameOn: boolean;
  tradingName: string;
  analysis?: CompanyAnalysis;
  /** The years the current analysis was run on, to spot a stale result. */
  analysedSelection?: string[];
};

export function CompanyRow({
  picked,
  onToggleFiling,
  onRemove,
  onToggleTradingName,
  onTradingNameChange,
  onAnalyse,
  disabled,
}: {
  picked: Picked;
  onToggleFiling: (companyNumber: string, transactionId: string) => void;
  onRemove: (companyNumber: string) => void;
  onToggleTradingName: (companyNumber: string) => void;
  onTradingNameChange: (companyNumber: string, value: string) => void;
  onAnalyse: (companyNumber: string) => void;
  disabled: boolean;
}) {
  const [open, setOpen] = useState(false);
  const { profile, filings, selected, analysis } = picked;

  const pages = filings
    .filter((f) => selected.includes(f.transaction_id))
    .reduce((n, f) => n + (f.pages ?? 0), 0);
  const cost = estimateCost(pages);
  const running = analysis?.status === "running";
  const stale =
    analysis !== undefined &&
    picked.analysedSelection !== undefined &&
    (picked.analysedSelection.length !== selected.length ||
      !picked.analysedSelection.every((t) => selected.includes(t)));
  const label = running
    ? "Analysing…"
    : analysis === undefined
      ? "Analyse"
      : stale
        ? "Re-analyse"
        : analysis.status === "error"
          ? "Try again"
          : "Analysed";

  return (
    <li className="border-b border-line px-4 py-3 last:border-b-0">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-ink" title={profile.company_name}>
            {profile.company_name}
          </p>
          <p className="mt-0.5 flex items-center gap-1.5 text-xs text-muted">
            <span className="num">{profile.company_number}</span>
            <StatusBadge status={profile.company_status} />
          </p>
        </div>
        <button
          type="button"
          onClick={() => onRemove(profile.company_number)}
          aria-label={`Remove ${profile.company_name}`}
          title={`Remove ${profile.company_name}`}
          className="flex shrink-0 items-center gap-1 rounded-md border border-line px-1.5 py-1 text-xs text-muted shadow-btn transition-colors hover:border-red-300 hover:bg-red-50 hover:text-red-600 dark:hover:border-red-900 dark:hover:bg-red-950/40"
        >
          <svg viewBox="0 0 16 16" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
            <path d="M4 4l8 8M12 4l-8 8" />
          </svg>
          Remove
        </button>
      </div>

      <div className="mt-2.5">
        {picked.loading ? (
          <p className="text-xs text-muted">Loading filings…</p>
        ) : picked.error ? (
          <p className="text-xs text-red-600">{picked.error}</p>
        ) : filings.length === 0 ? (
          <p className="text-xs text-muted">No accounts filed yet.</p>
        ) : (
          <>
            <YearPills
              filings={filings}
              selected={selected}
              maxSelected={MAX_FILINGS_PER_COMPANY}
              onToggle={(txn) => onToggleFiling(profile.company_number, txn)}
            />
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              className="mt-2 text-xs text-muted hover:text-accent"
            >
              {open ? "Hide filings" : `${filings.length} filings · PDFs`}
            </button>
            <div className="mt-2.5">
                <label className="flex items-center gap-1.5 text-xs text-muted">
                  <input
                    type="checkbox"
                    checked={picked.tradingNameOn}
                    onChange={() => onToggleTradingName(profile.company_number)}
                    className="checkbox"
                  />
                  Trades under a different name
                </label>
                {picked.tradingNameOn && (
                  <input
                    value={picked.tradingName}
                    onChange={(e) =>
                      onTradingNameChange(profile.company_number, e.target.value)
                    }
                    placeholder="Name used online"
                    aria-label={`Trading name for ${profile.company_name}`}
                    className="input mt-1.5 text-xs"
                  />
                )}
            </div>
            <div className="mt-2.5 flex items-center justify-between gap-2">
              <span className="text-xs text-subtle">
                {selected.length === 0
                  ? "Pick a year"
                  : [
                      `${selected.length} ${selected.length === 1 ? "year" : "years"}`,
                      pages > 0 ? `${pages}p` : null,
                      cost ? `${cost} + web` : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
              </span>
              <button
                type="button"
                onClick={() => onAnalyse(profile.company_number)}
                disabled={
                  disabled ||
                  running ||
                  selected.length === 0 ||
                  (analysis?.status === "done" && !stale)
                }
                className="btn-primary px-2.5 py-1 text-xs"
              >
                {label}
              </button>
            </div>
            {open && (
              <ul className="mt-1.5 space-y-1 border-l border-line pl-2.5">
                {filings.map((f) => (
                  <li key={f.transaction_id} className="flex items-baseline justify-between gap-2 text-xs">
                    <span className="num text-muted">
                      {f.made_up_to ?? f.date}
                      {f.paper_filed && <span className="ml-1 text-amber-600">scan</span>}
                    </span>
                    <span className="flex items-baseline gap-2">
                      <span className="num text-subtle">{f.pages ? `${f.pages}p` : ""}</span>
                      {f.downloadable ? (
                        <a
                          href={filingPdfUrl(profile.company_number, f.transaction_id)}
                          target="_blank"
                          rel="noreferrer"
                          className="text-accent hover:underline"
                        >
                          PDF
                        </a>
                      ) : (
                        <span className="text-subtle">n/a</span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </li>
  );
}
