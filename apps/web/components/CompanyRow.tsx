"use client";

import { useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import { YearPills } from "@/components/YearPills";
import { MAX_FILINGS_PER_COMPANY, filingPdfUrl } from "@/lib/api";
import type { CompanyProfile, Filing } from "@/lib/api";

export type Picked = {
  profile: CompanyProfile;
  filings: Filing[];
  selected: string[];
  loading: boolean;
  error?: string;
  tradingNameOn: boolean;
  tradingName: string;
};

export function CompanyRow({
  picked,
  onToggleFiling,
  onRemove,
  onToggleTradingName,
  onTradingNameChange,
  showTradingName,
}: {
  picked: Picked;
  onToggleFiling: (companyNumber: string, transactionId: string) => void;
  onRemove: (companyNumber: string) => void;
  onToggleTradingName: (companyNumber: string) => void;
  onTradingNameChange: (companyNumber: string, value: string) => void;
  /** Only relevant when web research is on — it is what the search keys off. */
  showTradingName: boolean;
}) {
  const [open, setOpen] = useState(false);
  const { profile, filings, selected } = picked;

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
          className="shrink-0 rounded p-1 text-subtle hover:bg-canvas hover:text-red-600"
        >
          <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
            <path d="M4 4l8 8M12 4l-8 8" />
          </svg>
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
            {showTradingName && (
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
            )}
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
