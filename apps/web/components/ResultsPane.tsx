"use client";

import { useEffect, useRef, useState } from "react";
import { Markdown } from "@/components/Markdown";
import { fmtBytes } from "@/lib/api";
import type { AnalysisJob, CompanyRun } from "@/lib/api";

const COMPARISON_TAB = "__comparison__";

export function ResultsPane({ job }: { job: AnalysisJob | null }) {
  const [tab, setTab] = useState<string>(COMPARISON_TAB);
  const userPicked = useRef(false);

  // Follow the run until the reader chooses a tab themselves: show the first
  // company that finishes, then switch to the comparison when it lands.
  useEffect(() => {
    if (!job || userPicked.current) return;
    if (job.comparison_markdown) {
      setTab(COMPARISON_TAB);
      return;
    }
    const firstDone = job.companies.find((c) => c.status === "done");
    if (firstDone) setTab(firstDone.company_number);
  }, [job]);

  useEffect(() => {
    userPicked.current = false;
    setTab(COMPARISON_TAB);
  }, [job?.id]);

  if (!job) return <EmptyState />;

  const multi = job.companies.length > 1;
  const active =
    tab === COMPARISON_TAB
      ? null
      : job.companies.find((c) => c.company_number === tab) ?? null;
  const showComparison = tab === COMPARISON_TAB;

  return (
    <div className="space-y-4">
      {job.status === "running" && (
        <div className="card card-body flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="card-title">
              Reviewing {job.finished} of {job.total}
              {job.total === 1 ? " company" : " companies"}…
            </p>
            <p className="mt-0.5 text-xs text-muted">
              Each company is read from its own filings, then compared. A minute or two
              per company.
            </p>
          </div>
          <Spinner />
        </div>
      )}

      <div className="card">
        <div className="flex items-center gap-1 overflow-x-auto border-b border-line px-2">
          {multi && (
            <Tab
              active={showComparison}
              onClick={() => {
                userPicked.current = true;
                setTab(COMPARISON_TAB);
              }}
              status={
                job.comparison_markdown
                  ? "done"
                  : job.comparison_error
                    ? "error"
                    : job.status === "running"
                      ? "running"
                      : "pending"
              }
            >
              Comparison
            </Tab>
          )}
          {job.companies.map((c) => (
            <Tab
              key={c.company_number}
              active={active?.company_number === c.company_number}
              onClick={() => {
                userPicked.current = true;
                setTab(c.company_number);
              }}
              status={c.status}
            >
              {c.company_name || c.company_number}
            </Tab>
          ))}
        </div>

        <div className="card-body">
          {showComparison ? (
            multi ? (
              job.comparison_markdown ? (
                <>
                  <Header title="Comparison" text={job.comparison_markdown} />
                  <Markdown>{job.comparison_markdown}</Markdown>
                </>
              ) : job.comparison_error ? (
                <p className="text-sm text-amber-700 dark:text-amber-300">
                  {job.comparison_error}
                </p>
              ) : (
                <p className="text-sm text-muted">
                  The comparison is written once every company has been reviewed.
                </p>
              )
            ) : null
          ) : active ? (
            active.status === "done" && active.markdown ? (
              <>
                <Header
                  title={active.company_name}
                  subtitle={active.filings
                    .map((f) => `${f.made_up_to ?? f.date} (${fmtBytes(f.size_bytes)})`)
                    .join(" · ")}
                  text={active.markdown}
                />
                <Markdown>{active.markdown}</Markdown>
              </>
            ) : active.status === "error" ? (
              <p className="text-sm text-red-600">{active.error}</p>
            ) : (
              <p className="text-sm text-muted">
                {active.status === "running" ? "Reading filings…" : "Queued"}
              </p>
            )
          ) : null}
        </div>
      </div>

      {job.status !== "running" && (
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

function Header({
  title,
  subtitle,
  text,
}: {
  title: string;
  subtitle?: string;
  text: string;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="mb-4 flex flex-wrap items-start justify-between gap-3 border-b border-line pb-3">
      <div className="min-w-0">
        <h2 className="text-base font-semibold text-ink">{title}</h2>
        {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
      </div>
      <button
        type="button"
        onClick={() => {
          navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        }}
        className="btn-secondary shrink-0"
      >
        {copied ? "Copied" : "Copy Markdown"}
      </button>
    </div>
  );
}

function Tab({
  active,
  onClick,
  status,
  children,
}: {
  active: boolean;
  onClick: () => void;
  status: CompanyRun["status"] | "error";
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex max-w-[14rem] items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2.5 text-sm transition-colors ${
        active
          ? "border-accent font-semibold text-accent"
          : "border-transparent text-muted hover:text-ink"
      }`}
    >
      <Dot status={status} />
      <span className="truncate">{children}</span>
    </button>
  );
}

function Dot({ status }: { status: string }) {
  const tone =
    status === "done"
      ? "bg-emerald-500"
      : status === "error"
        ? "bg-amber-500"
        : status === "running"
          ? "bg-accent animate-pulse"
          : "bg-line";
  return <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${tone}`} aria-hidden />;
}

function EmptyState() {
  return (
    <div className="card card-body">
      <h2 className="text-base font-semibold text-ink">Nothing reviewed yet</h2>
      <p className="mt-1 text-sm text-muted">
        Build a list of companies, then run the review.
      </p>
      <ol className="mt-4 space-y-3">
        {[
          ["Search and add companies", "Up to five at a time."],
          [
            "Pick the years you want",
            "Each company lists the years it has filed accounts for; tick up to four.",
          ],
          [
            "Review with Claude",
            "Every company is read from its own filed PDFs, then compared side by side.",
          ],
        ].map(([title, body], i) => (
          <li key={title} className="flex gap-3">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold text-accent">
              {i + 1}
            </span>
            <span className="text-sm">
              <span className="font-medium text-ink">{title}</span>
              <span className="block text-muted">{body}</span>
            </span>
          </li>
        ))}
      </ol>
      <p className="mt-5 border-t border-line pt-4 text-xs text-subtle">
        Most small UK companies file filleted or micro-entity accounts with no profit and
        loss account, so turnover and profit are often simply not disclosed. Claude will
        say so rather than estimate.
      </p>
    </div>
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
