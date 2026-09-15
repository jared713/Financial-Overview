"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Banner } from "@/components/Banner";
import { CompanyCard } from "@/components/CompanyCard";
import type { Picked } from "@/components/CompanyCard";
import { ResultsPanel } from "@/components/ResultsPanel";
import { StatusBadge } from "@/components/StatusBadge";
import {
  MAX_COMPANIES,
  MAX_FILINGS_PER_COMPANY,
  api,
  estimateCost,
} from "@/lib/api";
import type { AnalysisJob, CompanyHit, FilingFeatures } from "@/lib/api";

const POLL_MS = 2500;

export default function Page() {
  const [features, setFeatures] = useState<FilingFeatures | null>(null);

  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<CompanyHit[] | null>(null);
  const [searching, setSearching] = useState(false);

  const [picked, setPicked] = useState<Picked[]>([]);
  const [question, setQuestion] = useState("");

  const [job, setJob] = useState<AnalysisJob | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.filingFeatures().then(setFeatures).catch(() => setFeatures(null));
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  async function search() {
    if (!query.trim()) return;
    setSearching(true);
    setError(null);
    try {
      setHits(await api.searchCompanies(query.trim()));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setHits(null);
    } finally {
      setSearching(false);
    }
  }

  async function addCompany(hit: CompanyHit) {
    if (picked.some((p) => p.profile.company_number === hit.company_number)) return;
    if (picked.length >= MAX_COMPANIES) return;

    // Show the card immediately, fill in the filings when they arrive.
    const placeholder: Picked = {
      profile: {
        company_number: hit.company_number,
        company_name: hit.title,
        company_status: hit.company_status,
        company_type: hit.company_type,
        sic_codes: [],
      },
      filings: [],
      selected: [],
      loading: true,
    };
    setPicked((current) => [...current, placeholder]);

    try {
      const [profile, filings] = await Promise.all([
        api.company(hit.company_number),
        api.companyFilings(hit.company_number),
      ]);
      // Preselect the two most recent downloadable filings — enough for a
      // year-on-year read per company; tick more for a longer trend.
      const selected = filings
        .filter((f) => f.downloadable)
        .slice(0, 2)
        .map((f) => f.transaction_id);
      setPicked((current) =>
        current.map((p) =>
          p.profile.company_number === hit.company_number
            ? { profile, filings, selected, loading: false }
            : p,
        ),
      );
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setPicked((current) =>
        current.map((p) =>
          p.profile.company_number === hit.company_number
            ? { ...p, loading: false, error: message }
            : p,
        ),
      );
    }
  }

  function removeCompany(companyNumber: string) {
    setPicked((current) => current.filter((p) => p.profile.company_number !== companyNumber));
  }

  function toggleFiling(companyNumber: string, transactionId: string) {
    setPicked((current) =>
      current.map((p) => {
        if (p.profile.company_number !== companyNumber) return p;
        const has = p.selected.includes(transactionId);
        if (!has && p.selected.length >= MAX_FILINGS_PER_COMPANY) return p;
        return {
          ...p,
          selected: has
            ? p.selected.filter((t) => t !== transactionId)
            : [...p.selected, transactionId],
        };
      }),
    );
  }

  async function run() {
    const companies = picked
      .filter((p) => p.selected.length > 0)
      .map((p) => ({
        company_number: p.profile.company_number,
        transaction_ids: p.selected,
      }));
    if (companies.length === 0) return;

    setStarting(true);
    setError(null);
    setJob(null);
    stopPolling();
    try {
      const started = await api.startAnalysis(companies, question);
      setJob(started);
      requestAnimationFrame(() =>
        resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
      );
      pollRef.current = setInterval(async () => {
        try {
          const next = await api.analysis(started.id);
          setJob(next);
          if (next.status !== "running") stopPolling();
        } catch (e) {
          stopPolling();
          setError(e instanceof Error ? e.message : String(e));
        }
      }, POLL_MS);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setStarting(false);
    }
  }

  const claudeOff = features !== null && !features.claude_review;
  const chOff = features !== null && !features.companies_house;
  const readyCompanies = picked.filter((p) => p.selected.length > 0);
  const filingCount = readyCompanies.reduce((n, p) => n + p.selected.length, 0);
  const pageCount = readyCompanies.reduce(
    (n, p) =>
      n +
      p.filings
        .filter((f) => p.selected.includes(f.transaction_id))
        .reduce((m, f) => m + (f.pages ?? 0), 0),
    0,
  );
  const cost = estimateCost(pageCount, features?.model);
  const busy = job?.status === "running" || starting;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="page-title">UK company accounts</h1>
        <p className="page-subtitle">
          Pick up to {MAX_COMPANIES} companies and the years you want. Claude reviews each
          company from its filed accounts, then compares them.
        </p>
      </header>

      {chOff && (
        <Banner tone="red">
          <code className="font-mono text-xs">COMPANIES_HOUSE_API_KEY</code> is not set on
          the API service, so search and downloads are unavailable.
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
            Add a company
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
                  const added = picked.some(
                    (p) => p.profile.company_number === hit.company_number,
                  );
                  const full = picked.length >= MAX_COMPANIES;
                  return (
                    <li
                      key={hit.company_number}
                      className="flex items-center justify-between gap-4 border-b border-line px-5 py-3 last:border-b-0"
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
                      <span className="flex shrink-0 items-center gap-3">
                        <StatusBadge status={hit.company_status} />
                        <span className="num text-xs text-muted">{hit.company_number}</span>
                        <button
                          type="button"
                          onClick={() => addCompany(hit)}
                          disabled={added || full}
                          className="btn-secondary"
                        >
                          {added ? "Added" : "Add"}
                        </button>
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        )}
      </section>

      {error && <Banner tone="red">{error}</Banner>}

      {picked.map((p) => (
        <CompanyCard
          key={p.profile.company_number}
          picked={p}
          onToggleFiling={toggleFiling}
          onRemove={removeCompany}
        />
      ))}

      {picked.length > 0 && (
        <section className="card card-body space-y-3">
          <div>
            <label className="label" htmlFor="question">
              Optional question for Claude
            </label>
            <textarea
              id="question"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              rows={2}
              placeholder="e.g. Which of these has the strongest balance sheet, and why?"
              className="input mt-2 resize-y"
            />
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={run}
              disabled={busy || readyCompanies.length === 0 || claudeOff}
              className="btn-primary"
            >
              {busy
                ? "Reviewing…"
                : readyCompanies.length > 1
                  ? `Review and compare ${readyCompanies.length} companies`
                  : "Review with Claude"}
            </button>
            <span className="text-xs text-muted">
              {readyCompanies.length}
              {readyCompanies.length === 1 ? " company" : " companies"} · {filingCount}
              {filingCount === 1 ? " filing" : " filings"}
              {pageCount > 0 && ` · ${pageCount} pages`}
              {cost && ` · ${cost} estimated`}
            </span>
          </div>
        </section>
      )}

      <div ref={resultsRef}>{job && <ResultsPanel job={job} />}</div>
    </div>
  );
}
