"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Banner } from "@/components/Banner";
import type { Picked } from "@/components/CompanyRow";
import { ResultsPane } from "@/components/ResultsPane";
import { SelectionRail } from "@/components/SelectionRail";
import { MAX_COMPANIES, MAX_FILINGS_PER_COMPANY, api, estimateCost } from "@/lib/api";
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

    // Show the row immediately, fill in the filings when they arrive.
    setPicked((current) => [
      ...current,
      {
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
      },
    ]);

    try {
      const [profile, filings] = await Promise.all([
        api.company(hit.company_number),
        api.companyFilings(hit.company_number),
      ]);
      // Preselect the two most recent years — enough for a year-on-year read;
      // tick more for a longer trend.
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
  const ready = picked.filter((p) => p.selected.length > 0);
  const filingCount = ready.reduce((n, p) => n + p.selected.length, 0);
  const pageCount = ready.reduce(
    (n, p) =>
      n +
      p.filings
        .filter((f) => p.selected.includes(f.transaction_id))
        .reduce((m, f) => m + (f.pages ?? 0), 0),
    0,
  );
  const cost = estimateCost(pageCount, features?.model);
  const busy = job?.status === "running" || starting;

  const summary =
    ready.length === 0
      ? "Pick at least one year of accounts."
      : [
          `${ready.length} ${ready.length === 1 ? "company" : "companies"}`,
          `${filingCount} ${filingCount === 1 ? "filing" : "filings"}`,
          pageCount > 0 ? `${pageCount} pages` : null,
          cost ? `${cost} estimated` : null,
        ]
          .filter(Boolean)
          .join(" · ");

  return (
    <div className="lg:grid lg:grid-cols-[22rem_minmax(0,1fr)]">
      <aside className="border-b border-line bg-surface lg:sticky lg:top-14 lg:h-[calc(100vh-3.5rem)] lg:overflow-hidden lg:border-b-0 lg:border-r">
        <SelectionRail
          query={query}
          onQueryChange={setQuery}
          onSearch={search}
          searching={searching}
          hits={hits}
          picked={picked}
          onAdd={addCompany}
          onRemove={removeCompany}
          onToggleFiling={toggleFiling}
          question={question}
          onQuestionChange={setQuestion}
          onRun={run}
          busy={busy}
          canRun={ready.length > 0 && !claudeOff}
          summary={summary}
          disabled={chOff}
        />
      </aside>

      <main className="min-w-0 space-y-4 px-5 py-6 sm:px-8">
        {/* Cap the reading width so tables and prose stay legible on wide screens. */}
        <div className="mx-auto w-full max-w-5xl space-y-4">
        <header>
          <h1 className="page-title">UK company accounts</h1>
          <p className="page-subtitle">
            Claude reviews each company from its filed accounts, then compares them.
          </p>
        </header>

        {chOff && (
          <Banner tone="red">
            <code className="font-mono text-xs">COMPANIES_HOUSE_API_KEY</code> is not set
            on the API service, so search and downloads are unavailable.
          </Banner>
        )}
        {claudeOff && !chOff && (
          <Banner tone="amber">
            <code className="font-mono text-xs">ANTHROPIC_API_KEY</code> is not set on the
            API service. Filings can be searched and downloaded, but Claude review is
            switched off.
          </Banner>
        )}
        {error && <Banner tone="red">{error}</Banner>}

        <ResultsPane job={job} />
        </div>
      </main>
    </div>
  );
}
