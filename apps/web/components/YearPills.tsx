"use client";

import type { Filing } from "@/lib/api";

/** Filings are chosen by year, so label each one by its period end. Two filings
 *  can land in the same calendar year (a changed year end), so disambiguate
 *  those with the month rather than showing two identical pills. */
export function filingLabels(filings: Filing[]): Map<string, string> {
  const labels = new Map<string, string>();
  const years = new Map<string, number>();
  for (const f of filings) {
    const stamp = f.made_up_to ?? f.date ?? "";
    const year = stamp.slice(0, 4) || "—";
    years.set(year, (years.get(year) ?? 0) + 1);
  }
  for (const f of filings) {
    const stamp = f.made_up_to ?? f.date ?? "";
    const year = stamp.slice(0, 4) || "—";
    const month = stamp.slice(5, 7);
    const clash = (years.get(year) ?? 0) > 1;
    labels.set(f.transaction_id, clash && month ? `${year}/${month}` : year);
  }
  return labels;
}

export function YearPills({
  filings,
  selected,
  maxSelected,
  onToggle,
}: {
  filings: Filing[];
  selected: string[];
  maxSelected: number;
  onToggle: (transactionId: string) => void;
}) {
  const labels = filingLabels(filings);
  return (
    <div className="flex flex-wrap gap-1.5">
      {filings.map((f) => {
        const on = selected.includes(f.transaction_id);
        const atLimit = !on && selected.length >= maxSelected;
        const disabled = !f.downloadable || atLimit;
        return (
          <button
            key={f.transaction_id}
            type="button"
            aria-pressed={on}
            disabled={disabled}
            onClick={() => onToggle(f.transaction_id)}
            title={
              f.downloadable
                ? `Accounts to ${f.made_up_to ?? "?"}, filed ${f.date ?? "?"}${
                    f.pages ? `, ${f.pages} pages` : ""
                  }`
                : "No document available for this filing"
            }
            className={`num rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors ${
              on
                ? "border-accent bg-accent text-[rgb(var(--on-accent))]"
                : disabled
                  ? "cursor-not-allowed border-line text-subtle"
                  : "border-line text-body hover:border-accent hover:text-accent"
            }`}
          >
            {labels.get(f.transaction_id)}
          </button>
        );
      })}
    </div>
  );
}
