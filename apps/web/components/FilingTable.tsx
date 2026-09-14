"use client";

import type { Filing } from "@/lib/api";
import { filingPdfUrl } from "@/lib/api";

const MAX_SELECTED = 6;

/** Companies House descriptions are slugs like
 *  "accounts-with-accounts-type-total-exemption-full" — show the part that
 *  actually distinguishes one filing from another. */
function accountsType(filing: Filing): string {
  const raw = (filing.description ?? filing.type ?? "")
    .replace(/^accounts-with-accounts-type-/, "")
    .replace(/^accounts-?/, "");
  const text = (raw || filing.type || "accounts").replace(/-/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function FilingTable({
  companyNumber,
  filings,
  selected,
  onToggle,
}: {
  companyNumber: string;
  filings: Filing[];
  selected: string[];
  onToggle: (transactionId: string) => void;
}) {
  if (filings.length === 0) {
    return (
      <p className="px-5 py-6 text-sm text-muted">
        No accounts filings found for this company. Newly incorporated companies have
        none until their first accounts are due.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="table min-w-[42rem]">
        <thead>
          <tr>
            <th className="w-10 pr-0"></th>
            <th>Period end</th>
            <th>Filed</th>
            <th>Type</th>
            <th className="text-right">Pages</th>
            <th className="text-right">PDF</th>
          </tr>
        </thead>
        <tbody>
          {filings.map((f) => {
            const isSelected = selected.includes(f.transaction_id);
            const atLimit = !isSelected && selected.length >= MAX_SELECTED;
            return (
              <tr
                key={f.transaction_id}
                className={isSelected ? "bg-accent-soft/60" : "hover:bg-canvas"}
              >
                <td className="pr-0">
                  <input
                    type="checkbox"
                    checked={isSelected}
                    disabled={!f.downloadable || atLimit}
                    onChange={() => onToggle(f.transaction_id)}
                    aria-label={`Select accounts made up to ${f.made_up_to ?? f.date}`}
                    className="checkbox"
                  />
                </td>
                <td className="num font-medium text-ink">{f.made_up_to ?? "—"}</td>
                <td className="num text-muted">{f.date ?? "—"}</td>
                <td>
                  {accountsType(f)}
                  {f.paper_filed && <span className="badge-amber ml-2">scanned</span>}
                </td>
                <td className="num text-right text-muted">{f.pages ?? "—"}</td>
                <td className="text-right">
                  {f.downloadable ? (
                    <a
                      href={filingPdfUrl(companyNumber, f.transaction_id)}
                      target="_blank"
                      rel="noreferrer"
                      className="btn-link"
                    >
                      Open
                    </a>
                  ) : (
                    <span className="text-subtle">n/a</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export { MAX_SELECTED };
