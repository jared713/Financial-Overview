"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Banner } from "@/components/Banner";
import type { Picked } from "@/components/CompanyRow";
import { ResultsPane } from "@/components/ResultsPane";
import type { ResultTab } from "@/components/ResultsPane";
import { SavedDrawer } from "@/components/SavedDrawer";
import { SelectionRail } from "@/components/SelectionRail";
import { MAX_COMPANIES, MAX_FILINGS_PER_COMPANY, api } from "@/lib/api";
import type { CompanyHit, Comparison, FilingFeatures, SavedItem } from "@/lib/api";

const POLL_MS = 2500;

export default function Page() {
  const [features, setFeatures] = useState<FilingFeatures | null>(null);

  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<CompanyHit[] | null>(null);
  const [searching, setSearching] = useState(false);

  const [picked, setPicked] = useState<Picked[]>([]);

  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [guidance, setGuidance] = useState("");
  const [focusId, setFocusId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Items opened from the saved library, which are not part of the working list.
  const [extraTabs, setExtraTabs] = useState<ResultTab[]>([]);
  const [savedOpen, setSavedOpen] = useState(false);
  const [savedReloadKey, setSavedReloadKey] = useState(0);

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

  // One timer polls everything still running — analyses and the comparison —
  // and stops itself once nothing is.
  const ensurePolling = useCallback(() => {
    if (pollRef.current) return;
    pollRef.current = setInterval(async () => {
      let running = 0;
      try {
        const current = pickedRef.current;
        for (const p of current) {
          if (p.analysis?.status === "running") {
            running += 1;
            const next = await api.companyAnalysis(p.analysis.id);
            setPicked((list) =>
              list.map((item) =>
                item.profile.company_number === p.profile.company_number
                  ? { ...item, analysis: next }
                  : item,
              ),
            );
          }
        }
        const currentComparison = comparisonRef.current;
        if (currentComparison?.status === "running") {
          running += 1;
          setComparison(await api.comparison(currentComparison.id));
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        stopPolling();
        return;
      }
      if (running === 0) {
        stopPolling();
        setSavedReloadKey((n) => n + 1);
      }
    }, POLL_MS);
  }, [stopPolling]);

  // Refs so the interval always reads current state without being re-created.
  const pickedRef = useRef<Picked[]>([]);
  const comparisonRef = useRef<Comparison | null>(null);
  useEffect(() => {
    pickedRef.current = picked;
  }, [picked]);
  useEffect(() => {
    comparisonRef.current = comparison;
  }, [comparison]);

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

  function clearSearch() {
    setQuery("");
    setHits(null);
  }

  async function addCompany(hit: CompanyHit) {
    if (picked.some((p) => p.profile.company_number === hit.company_number)) return;
    if (picked.length >= MAX_COMPANIES) return;

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
        tradingNameOn: false,
        tradingName: "",
      },
    ]);

    try {
      const [profile, filings] = await Promise.all([
        api.company(hit.company_number),
        api.companyFilings(hit.company_number),
      ]);
      const selected = filings
        .filter((f) => f.downloadable)
        .slice(0, 2)
        .map((f) => f.transaction_id);
      setPicked((current) =>
        current.map((p) =>
          p.profile.company_number === hit.company_number
            ? { ...p, profile, filings, selected, loading: false }
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

  function toggleTradingName(companyNumber: string) {
    setPicked((current) =>
      current.map((p) =>
        p.profile.company_number === companyNumber
          ? { ...p, tradingNameOn: !p.tradingNameOn }
          : p,
      ),
    );
  }

  function setTradingName(companyNumber: string, value: string) {
    setPicked((current) =>
      current.map((p) =>
        p.profile.company_number === companyNumber ? { ...p, tradingName: value } : p,
      ),
    );
  }

  async function analyseCompany(companyNumber: string) {
    const target = picked.find((p) => p.profile.company_number === companyNumber);
    if (!target || target.selected.length === 0) return;
    setError(null);
    try {
      const analysis = await api.analyseCompany({
        company_number: companyNumber,
        transaction_ids: target.selected,
        trading_name:
          target.tradingNameOn && target.tradingName.trim()
            ? target.tradingName.trim()
            : null,
      });
      setPicked((current) =>
        current.map((p) =>
          p.profile.company_number === companyNumber
            ? { ...p, analysis, analysedSelection: [...target.selected] }
            : p,
        ),
      );
      setFocusId(analysis.id);
      ensurePolling();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function compare() {
    const ids = picked
      .filter((p) => p.analysis?.status === "done")
      .map((p) => p.analysis!.id);
    if (ids.length < 2) return;
    setError(null);
    try {
      const started = await api.compare(ids, guidance);
      setComparison(started);
      setFocusId(started.id);
      ensurePolling();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function openSavedItem(item: SavedItem) {
    setSavedOpen(false);
    setError(null);
    if (tabs.some((t) => t.id === item.id)) {
      setFocusId(item.id);
      return;
    }
    try {
      if (item.kind === "analysis") {
        const analysis = await api.companyAnalysis(item.id);
        setExtraTabs((current) => [
          ...current,
          {
            kind: "company",
            id: analysis.id,
            title: analysis.company_name || analysis.company_number,
            status: analysis.status,
            analysis,
          },
        ]);
      } else {
        const loaded = await api.comparison(item.id);
        setExtraTabs((current) => [
          ...current,
          {
            kind: "comparison",
            id: loaded.id,
            title: `Comparison · ${loaded.companies.length}`,
            status: loaded.status,
            comparison: loaded,
          },
        ]);
      }
      setFocusId(item.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const claudeOff = features !== null && !features.claude_review;
  const chOff = features !== null && !features.companies_house;
  const done = picked.filter((p) => p.analysis?.status === "done");
  const analysing = picked.some((p) => p.analysis?.status === "running");

  const liveTabs: ResultTab[] = [
    ...(comparison
      ? [
          {
            kind: "comparison" as const,
            id: comparison.id,
            title: "Comparison",
            status: comparison.status,
            comparison,
          },
        ]
      : []),
    ...picked
      .filter((p) => p.analysis !== undefined)
      .map((p) => ({
        kind: "company" as const,
        id: p.analysis!.id,
        title: p.analysis!.company_name || p.profile.company_name,
        status: p.analysis!.status,
        analysis: p.analysis!,
      })),
  ];
  // Library items the working list does not already cover.
  const tabs: ResultTab[] = [
    ...liveTabs,
    ...extraTabs.filter((t) => !liveTabs.some((live) => live.id === t.id)),
  ];

  const summary = analysing
    ? "Analysing… you can add and analyse others meanwhile."
    : done.length >= 2
      ? `${done.length} analysed and ready to compare.`
      : done.length === 1
        ? "Analyse a second company to compare."
        : "Analyse a company to get started.";

  return (
    <div className="lg:grid lg:grid-cols-[22rem_minmax(0,1fr)]">
      <aside className="border-b border-line bg-surface lg:sticky lg:top-14 lg:h-[calc(100vh-3.5rem)] lg:overflow-hidden lg:border-b-0 lg:border-r">
        <SelectionRail
          query={query}
          onQueryChange={setQuery}
          onSearch={search}
          onClearSearch={clearSearch}
          searching={searching}
          hits={hits}
          picked={picked}
          onAdd={addCompany}
          onRemove={removeCompany}
          onToggleFiling={toggleFiling}
          onToggleTradingName={toggleTradingName}
          onTradingNameChange={setTradingName}
          onAnalyse={analyseCompany}
          guidance={guidance}
          onGuidanceChange={setGuidance}
          onCompare={compare}
          comparing={comparison?.status === "running"}
          readyToCompare={done.length}
          summary={summary}
          disabled={chOff || claudeOff}
        />
      </aside>

      <main className="min-w-0 space-y-4 px-5 py-6 sm:px-8">
        <div className="mx-auto w-full max-w-5xl space-y-4">
          <header className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="page-title">UK company accounts</h1>
              <p className="page-subtitle">
                Analyse companies one at a time, then compare them when you are ready.
              </p>
            </div>
            <button type="button" onClick={() => setSavedOpen(true)} className="btn-secondary">
              Saved
            </button>
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
          {features?.saving_is_durable === false && (
            <Banner tone="amber">
              Results are being saved, but the API has no volume mounted, so they will be
              lost on the next deploy. Attach a Railway volume at{" "}
              <code className="font-mono text-xs">/data</code> to keep them.
            </Banner>
          )}
          {error && <Banner tone="red">{error}</Banner>}

          <ResultsPane tabs={tabs} focusId={focusId} />
        </div>
      </main>

      <SavedDrawer
        open={savedOpen}
        onClose={() => setSavedOpen(false)}
        onOpenItem={openSavedItem}
        reloadKey={savedReloadKey}
      />
    </div>
  );
}
