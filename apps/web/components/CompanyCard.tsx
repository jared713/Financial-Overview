"use client";

import { FilingTable } from "@/components/FilingTable";
import { MAX_FILINGS_PER_COMPANY } from "@/lib/api";
import type { CompanyProfile, Filing } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

export type Picked = {
  profile: CompanyProfile;
  filings: Filing[];
  selected: string[];
  loading: boolean;
  error?: string;
};

export function CompanyCard({
  picked,
  onToggleFiling,
  onRemove,
}: {
  picked: Picked;
  onToggleFiling: (companyNumber: string, transactionId: string) => void;
  onRemove: (companyNumber: string) => void;
}) {
  const { profile } = picked;
  return (
    <section className="card">
      <div className="card-header">
        <div className="min-w-0">
          <h3 className="card-title truncate">{profile.company_name}</h3>
          <p className="mt-0.5 text-xs text-muted">
            <span className="num">{profile.company_number}</span>
            {profile.company_type ? ` · ${profile.company_type}` : ""}
            {profile.accounts_last_made_up_to
              ? ` · last accounts to ${profile.accounts_last_made_up_to}`
              : ""}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <StatusBadge status={profile.company_status} />
          <button type="button" onClick={() => onRemove(profile.company_number)} className="text-xs font-medium text-muted hover:text-red-600">
            Remove
          </button>
        </div>
      </div>

      {picked.loading ? (
        <p className="px-5 py-6 text-sm text-muted">Loading filings…</p>
      ) : picked.error ? (
        <p className="px-5 py-6 text-sm text-red-600">{picked.error}</p>
      ) : (
        <>
          <FilingTable
            companyNumber={profile.company_number}
            filings={picked.filings}
            selected={picked.selected}
            onToggle={(txn) => onToggleFiling(profile.company_number, txn)}
            maxSelected={MAX_FILINGS_PER_COMPANY}
          />
          <p className="border-t border-line px-5 py-2.5 text-xs text-subtle">
            {picked.selected.length} of {MAX_FILINGS_PER_COMPANY} years selected
          </p>
        </>
      )}
    </section>
  );
}
