"use client";

import { useEffect, useRef, useState } from "react";
import { FilingTable, MAX_SELECTED } from "@/components/FilingTable";
import { Markdown } from "@/components/Markdown";
import { api, fmtBytes } from "@/lib/api";
import type {
  CompanyHit,
  CompanyProfile,
  Filing,
  FilingAnalysis,
  FilingFeatures,
} from "@/lib/api";

export default function Page() {
  const [features, setFeatures] = useState<FilingFeatures | null>(null);

  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<CompanyHit[] | null>(null);
  const [searching, setSearching] = useState(false);

  const [company, setCompany] = useState<CompanyProfile | null>(null);
  const [filings, setFilings] = useState<Filing[]>([]);
  const [loadingFilings, setLoadingFilings] = useState(false);

  const [selected, setSelected] = useState<string[]>([]);
  const [question, setQuestion] = useState("");

  const [analysis, setAnalysis] = useState<FilingAnalysis | null>(null);
  const [analysing, setAnalysing] = useState(false);
  const [elapsed, setElapsed] = useState(0);

  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const resultRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.filingFeatures().then(setFeatures).catch(() => setFeatures(null));
  }, []);

  useEffect(() => {
    if (!analysing) return;
    setElapsed(0);
    const started = Date.now();
    const id = setInterval(() => setElapsed(Math.round((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(id);
  }, [analysing]);

  async function search() {
    if (!query.trim()) return;
    setSearching(true);
    setError(null);
    setCompany(null);
    setFilings([]);
    setSelected([]);
    setAnalysis(null);
    try {
      setHits(await api.searchCompanies(query.trim()));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setHits(null);
    } finally {
      setSearching(false);
    }
  }

  async function pickCompany(companyNumber: string) {
    setLoadingFilings(true);
    setError(null);
    setAnalysis(null);
    setSelected([]);
    try {
      const [profile, rows] = await Promise.all([
        api.company(companyNumber),
        api.companyFilings(companyNumber),
      ]);
      setCompany(profile);
      setFilings(rows);
      // Preselect the two most recent downloadable filings — the common case is
      // "how does the latest year compare with the one before".
      setSelected(rows.filter((f) => f.downloadable).slice(0, 2).map((f) => f.transaction_id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingFilings(false);
    }
  }

  function toggle(transactionId: string) {
    setSelected((current) =>
      current.includes(transactionId)
        ? current.filter((t) => t !== transactionId)
        : [...current, transactionId],
    );
  }

  async function analyse() {
    if (!company || selected.length === 0) return;
    setAnalysing(true);
    setError(null);
    setAnalysis(null);
    try {
      // Send oldest first so the comparison reads left-to-right in time order.
      const ordered = filings
        .filter((f) => selected.includes(f.transaction_id))
        .slice()
        .reverse()
        .map((f) => f.transaction_id);
      const result = await api.analyseFilings(company.company_number, ordered, question);
      setAnalysis(result);
      requestAnimationFrame(() =>
        resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setAnalysing(false);
    }
  }

  const claudeOff = features !== null && !features.claude_review;
  const chOff = features !== null && !features.companies_house;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="page-title">UK company accounts</h1>
        <p className="page-subtitle">
          Search a company at Companies House, pull its filed accounts, and have Claude
          summarise one or compare several.
        </p>
      </header>

      {chOff && (
        <Banner tone="red">
          <code className="font-mono text-xs">COMPANIES_HOUSE_API_KEY</code> is not set on
          the API service, so search and downloads are unavailable. See{" "}
          <code className="font-mono text-xs">docs/SETUP.md</code>.
        </Banner>
      )}
      {claudeOff && !chOff && (
        <Banner tone="amber">
          <code className="font-mono text-xs">ANTHROPIC_API_KEY</code> is not set on the
          API service. Filings can be searched and downloaded, but Claude review is
          switched off.
        </Banner>
      )}

      <section className="card">
        <div className="card-body">
          <label className="label" htmlFor="company-search">
            Company
          </label>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <input
              id="company-search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && search()}
              placeholder="Name or number — e.g. Tesco PLC or 00445790"
              className="input min-w-[16rem] flex-1"
            />
            <button
              type="button"
              onClick={search}
              disabled={searching || !query.trim()}
              className="btn-primary"
            >
              {searching ? "Searching…" : "Search"}
            </button>
          </div>
        </div>

        {hits !== null && (
          <div className="border-t border-line">
            {hits.length === 0 ? (
              <p className="px-5 py-4 text-sm text-muted">No companies matched that search.</p>
            ) : (
              <ul>
                {hits.map((hit) => {
                  const active = company?.company_number === hit.company_number;
                  return (
                    <li key={hit.company_number} className="border-b border-line last:border-b-0">
                      <button
                        type="button"
                        onClick={() => pickCompany(hit.company_number)}
                        className={`flex w-full items-center justify-between gap-4 px-5 py-3 text-left transition-colors ${
                          active ? "bg-accent-soft" : "hover:bg-canvas"
                        }`}
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-medium text-ink">
                            {hit.title}
                          </span>
                          {hit.address_snippet && (
                            <span className="block truncate text-xs text-muted">
                              {hit.address_snippet}
                            </span>
                          )}
                        </span>
                        <span className="flex shrink-0 items-center gap-2">
                          <StatusBadge status={hit.company_status} />
                          <span className="num text-xs text-muted">{hit.company_number}</span>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        )}
      </section>

      {error && <Banner tone="red">{error}</Banner>}

      {loadingFilings && (
        <p className="text-sm text-muted">Loading filings…</p>
      )}

      {company && (
        <section className="card">
          <div className="card-header">
            <div>
              <h2 className="card-title">{company.company_name}</h2>
              <p className="mt-0.5 text-xs text-muted">
                <span className="num">{company.company_number}</span>
                {company.company_type ? ` · ${company.company_type}` : ""}
                {company.accounts_last_made_up_to
                  ? ` · last accounts to ${company.accounts_last_made_up_to}`
                  : ""}
                {company.registered_office ? ` · ${company.registered_office}` : ""}
              </p>
            </div>
            <StatusBadge status={company.company_status} />
          </div>

          <FilingTable
            companyNumber={company.company_number}
            filings={filings}
            selected={selected}
            onToggle={toggle}
          />

          <div className="space-y-3 border-t border-line px-5 py-4">
            <div>
              <label className="label" htmlFor="question">
                Optional question for Claude
              </label>
              <textarea
                id="question"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                rows={2}
                placeholder="e.g. Is the cash position improving, and what is driving it?"
                className="input mt-2 resize-y"
              />
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={analyse}
                disabled={analysing || selected.length === 0 || claudeOff}
                className="btn-primary"
              >
                {analysing
                  ? `Reading filings… ${elapsed}s`
                  : selected.length > 1
                    ? `Compare ${selected.length} filings with Claude`
                    : "Review filing with Claude"}
              </button>
              <span className="text-xs text-muted">
                {selected.length} of {MAX_SELECTED} selected
                {analysing && " · a few filings can take a minute or two"}
              </span>
            </div>
          </div>
        </section>
      )}

      <div ref={resultRef}>
        {analysis && (
          <section className="card">
            <div className="card-header">
              <div>
                <h2 className="card-title">Claude&rsquo;s review</h2>
                <p className="mt-0.5 text-xs text-muted">
                  {analysis.filings
                    .map((f) => `${f.made_up_to ?? f.date} (${fmtBytes(f.size_bytes)})`)
                    .join(" · ")}
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  navigator.clipboard.writeText(analysis.markdown);
                  setCopied(true);
                  setTimeout(() => setCopied(false), 2000);
                }}
                className="btn-secondary"
              >
                {copied ? "Copied" : "Copy Markdown"}
              </button>
            </div>
            <div className="card-body">
              <Markdown>{analysis.markdown}</Markdown>
            </div>
            <p className="border-t border-line px-5 py-3 text-xs text-subtle">
              {analysis.model}
              {analysis.input_tokens != null &&
                ` · ${analysis.input_tokens.toLocaleString()} in / ${analysis.output_tokens?.toLocaleString()} out tokens`}
              . Figures are read from the filed PDFs — check anything you rely on against
              the source document.
            </p>
          </section>
        )}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status?: string | null }) {
  if (!status) return null;
  const tone =
    status === "active"
      ? "badge-green"
      : status === "dissolved" || status.includes("liquidation")
        ? "badge-amber"
        : "badge-neutral";
  return <span className={tone}>{status.replace(/-/g, " ")}</span>;
}

function Banner({
  tone,
  children,
}: {
  tone: "red" | "amber";
  children: React.ReactNode;
}) {
  const tones = {
    red: "border-red-200 bg-red-50 text-red-800 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200",
    amber:
      "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200",
  };
  return (
    <div className={`rounded-lg border px-4 py-3 text-sm shadow-card ${tones[tone]}`}>
      {children}
    </div>
  );
}
