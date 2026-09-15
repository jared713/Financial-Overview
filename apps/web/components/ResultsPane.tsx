"use client";

import { useEffect, useRef, useState } from "react";
import { Markdown } from "@/components/Markdown";
import { fmtBytes } from "@/lib/api";
import type { CompanyAnalysis, Comparison, RunStatus } from "@/lib/api";

export type ResultTab =
  | { kind: "comparison"; id: string; title: string; status: RunStatus; comparison: Comparison }
  | { kind: "company"; id: string; title: string; status: RunStatus; analysis: CompanyAnalysis };

export function ResultsPane({
  tabs,
  focusId,
}: {
  tabs: ResultTab[];
  /** Set when a run is started, so the pane jumps to what you just asked for. */
  focusId: string | null;
}) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const lastFocus = useRef<string | null>(null);

  useEffect(() => {
    if (focusId && focusId !== lastFocus.current) {
      lastFocus.current = focusId;
      setActiveId(focusId);
    }
  }, [focusId]);

  // Keep a valid tab selected as tabs come and go.
  useEffect(() => {
    if (tabs.length === 0) {
      setActiveId(null);
      return;
    }
    setActiveId((current) =>
      current && tabs.some((t) => t.id === current) ? current : tabs[tabs.length - 1].id,
    );
  }, [tabs]);

  if (tabs.length === 0) return <EmptyState />;

  const active = tabs.find((t) => t.id === activeId) ?? tabs[tabs.length - 1];

  return (
    <div className="card">
      <div className="flex items-center gap-1 overflow-x-auto border-b border-line px-2">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveId(tab.id)}
            className={`flex max-w-[15rem] items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2.5 text-sm transition-colors ${
              tab.id === active.id
                ? "border-accent font-semibold text-accent"
                : "border-transparent text-muted hover:text-ink"
            }`}
          >
            <Dot status={tab.status} />
            <span className="truncate">{tab.title}</span>
          </button>
        ))}
      </div>

      <div className="card-body">
        {active.kind === "comparison" ? (
          <ComparisonBody comparison={active.comparison} />
        ) : (
          <AnalysisBody analysis={active.analysis} />
        )}
      </div>
    </div>
  );
}

function ComparisonBody({ comparison }: { comparison: Comparison }) {
  if (comparison.status === "running") {
    return (
      <Waiting label={`Comparing ${comparison.companies.length} companies…`} />
    );
  }
  if (comparison.status === "error") {
    return <p className="text-sm text-red-600">{comparison.error}</p>;
  }
  return (
    <>
      <Header
        title="Comparison"
        subtitle={comparison.companies.map((c) => c.company_name).join(" · ")}
        text={comparison.markdown ?? ""}
      />
      <Markdown>{comparison.markdown ?? ""}</Markdown>
      <Footer model={comparison.model} input={comparison.input_tokens} output={comparison.output_tokens} />
    </>
  );
}

function AnalysisBody({ analysis }: { analysis: CompanyAnalysis }) {
  if (analysis.status === "running") {
    return (
      <Waiting
        label={
          analysis.research
            ? "Reading filings, then the web…"
            : "Reading filings…"
        }
      />
    );
  }
  if (analysis.status === "error") {
    return <p className="text-sm text-red-600">{analysis.error}</p>;
  }
  return (
    <>
      <Header
        title={analysis.company_name || analysis.company_number}
        subtitle={analysis.filings
          .map((f) => `${f.made_up_to ?? f.date} (${fmtBytes(f.size_bytes)})`)
          .join(" · ")}
        text={
          analysis.research_markdown
            ? `${analysis.markdown}\n\n${analysis.research_markdown}`
            : (analysis.markdown ?? "")
        }
      />
      <Markdown>{analysis.markdown ?? ""}</Markdown>
      {analysis.research_markdown && (
        <div className="mt-6 border-t border-line pt-5">
          <p className="label mb-3">From the web</p>
          <Markdown>{analysis.research_markdown}</Markdown>
        </div>
      )}
      {analysis.research_error && (
        <p className="mt-6 border-t border-line pt-5 text-sm text-amber-700 dark:text-amber-300">
          Web research unavailable: {analysis.research_error}
        </p>
      )}
      <Footer model={analysis.model} input={analysis.input_tokens} output={analysis.output_tokens} />
    </>
  );
}

function Footer({
  model,
  input,
  output,
}: {
  model?: string | null;
  input: number;
  output: number;
}) {
  return (
    <p className="mt-6 border-t border-line pt-3 text-xs text-subtle">
      {model}
      {input > 0 && ` · ${input.toLocaleString()} in / ${output.toLocaleString()} out tokens`}
      . Figures are read from the filed PDFs — check anything you rely on against the
      source document.
    </p>
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

function Waiting({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 py-6">
      <Spinner />
      <span className="text-sm text-muted">{label}</span>
    </div>
  );
}

function Dot({ status }: { status: RunStatus }) {
  const tone =
    status === "done"
      ? "bg-emerald-500"
      : status === "error"
        ? "bg-amber-500"
        : "bg-accent animate-pulse";
  return <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${tone}`} aria-hidden />;
}

function EmptyState() {
  return (
    <div className="card card-body">
      <h2 className="text-base font-semibold text-ink">Nothing reviewed yet</h2>
      <p className="mt-1 text-sm text-muted">
        Add a company, pick its years, and analyse it. Each one opens in its own tab.
      </p>
      <ol className="mt-4 space-y-3">
        {[
          ["Add a company and pick its years", "Each company lists the years it has filed accounts for; tick up to four."],
          ["Analyse it", "Claude reads the filed PDFs and writes it up in a new tab. Repeat for up to five companies."],
          ["Compare when ready", "Once two or more are done, compare them — with an optional steer on what matters."],
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
