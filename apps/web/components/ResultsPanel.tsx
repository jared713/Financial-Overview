"use client";

import { Markdown } from "@/components/Markdown";
import { fmtBytes } from "@/lib/api";
import type { AnalysisJob, CompanyRun } from "@/lib/api";

export function ResultsPanel({ job }: { job: AnalysisJob }) {
  const running = job.status === "running";
  return (
    <div className="space-y-4">
      {running && (
        <section className="card card-body">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="card-title">
                Reviewing {job.finished} of {job.total}
                {job.total === 1 ? " company" : " companies"}…
              </h2>
              <p className="mt-0.5 text-xs text-muted">
                Each company is read from its own filings, then compared. This takes a
                minute or two per company.
              </p>
            </div>
            <Spinner />
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {job.companies.map((c) => (
              <span key={c.company_number} className={statusTone(c.status)}>
                {c.company_name || c.company_number}
                {c.status === "running" ? " · reading" : ""}
                {c.status === "pending" ? " · queued" : ""}
                {c.status === "error" ? " · failed" : ""}
              </span>
            ))}
          </div>
        </section>
      )}

      {job.comparison_markdown && (
        <section className="card">
          <div className="card-header">
            <h2 className="card-title">Comparison</h2>
            <CopyButton text={job.comparison_markdown} />
          </div>
          <div className="card-body">
            <Markdown>{job.comparison_markdown}</Markdown>
          </div>
        </section>
      )}

      {job.comparison_error && (
        <p className="text-sm text-amber-700 dark:text-amber-300">
          Comparison unavailable: {job.comparison_error}
        </p>
      )}

      {job.companies.map((run) => (
        <CompanyResult key={run.company_number} run={run} />
      ))}

      {!running && (
        <p className="text-xs text-subtle">
          {job.model}
          {job.input_tokens > 0 &&
            ` · ${job.input_tokens.toLocaleString()} in / ${job.output_tokens.toLocaleString()} out tokens`}
          . Figures are read from the filed PDFs — check anything you rely on against the
          source document.
        </p>
      )}
    </div>
  );
}

function CompanyResult({ run }: { run: CompanyRun }) {
  return (
    <section className="card">
      <div className="card-header">
        <div className="min-w-0">
          <h2 className="card-title truncate">{run.company_name || run.company_number}</h2>
          {run.filings.length > 0 && (
            <p className="mt-0.5 text-xs text-muted">
              {run.filings
                .map((f) => `${f.made_up_to ?? f.date} (${fmtBytes(f.size_bytes)})`)
                .join(" · ")}
            </p>
          )}
        </div>
        {run.markdown ? <CopyButton text={run.markdown} /> : <span className={statusTone(run.status)}>{run.status}</span>}
      </div>
      <div className="card-body">
        {run.status === "done" && run.markdown ? (
          <Markdown>{run.markdown}</Markdown>
        ) : run.status === "error" ? (
          <p className="text-sm text-red-600">{run.error}</p>
        ) : (
          <p className="text-sm text-muted">
            {run.status === "running" ? "Reading filings…" : "Queued"}
          </p>
        )}
      </div>
    </section>
  );
}

function statusTone(status: CompanyRun["status"]): string {
  if (status === "done") return "badge-green";
  if (status === "error") return "badge-amber";
  if (status === "running") return "badge-violet";
  return "badge-neutral";
}

function CopyButton({ text }: { text: string }) {
  return (
    <button
      type="button"
      onClick={() => navigator.clipboard.writeText(text)}
      className="btn-secondary"
    >
      Copy Markdown
    </button>
  );
}

function Spinner() {
  return (
    <svg className="h-4 w-4 animate-spin text-accent" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity="0.25" />
      <path d="M22 12a10 10 0 0 1-10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}
