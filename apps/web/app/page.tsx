"use client";

import { useState } from "react";
import { Banner } from "@/components/Banner";
import { ResultsPane } from "@/components/ResultsPane";
import { SavedDrawer } from "@/components/SavedDrawer";
import { SelectionRail } from "@/components/SelectionRail";
import { useWorkspace } from "@/components/WorkspaceProvider";

export default function Page() {
  const { features, error, savedReloadKey, companies } = useWorkspace();
  const [savedOpen, setSavedOpen] = useState(false);

  const claudeOff = features !== null && !features.claude_review;
  const chOff = features !== null && !features.companies_house;

  const ready = companies.picked.filter((p) => p.selected.length > 0);
  const done = companies.picked.filter((p) => p.analysis?.status === "done");
  const analysing = companies.picked.some((p) => p.analysis?.status === "running");

  const summary = analysing
    ? "Analysing… you can add and analyse others meanwhile."
    : done.length >= 2
      ? `${done.length} analysed and ready to compare.`
      : done.length === 1
        ? "Analyse a second company to compare."
        : ready.length > 0
          ? "Analyse a company to get started."
          : "Add a company to get started.";

  return (
    <div className="lg:grid lg:grid-cols-[22rem_minmax(0,1fr)]">
      <aside className="border-b border-line bg-surface lg:sticky lg:top-14 lg:h-[calc(100vh-3.5rem)] lg:overflow-hidden lg:border-b-0 lg:border-r">
        <SelectionRail
          query={companies.query}
          onQueryChange={companies.setQuery}
          onSearch={companies.search}
          onClearSearch={companies.clearSearch}
          searching={companies.searching}
          hits={companies.hits}
          picked={companies.picked}
          onAdd={companies.add}
          onRemove={companies.remove}
          onToggleFiling={companies.toggleFiling}
          onToggleTradingName={companies.toggleTradingName}
          onTradingNameChange={companies.setTradingName}
          onAnalyse={companies.analyse}
          guidance={companies.guidance}
          onGuidanceChange={companies.setGuidance}
          onCompare={companies.compare}
          comparing={companies.comparison?.status === "running"}
          readyToCompare={done.length}
          summary={summary}
          disabled={chOff || claudeOff}
        />
      </aside>

      <main className="min-w-0 space-y-4 px-5 py-6 sm:px-8">
        <div className="mx-auto w-full max-w-5xl space-y-4">
          <header className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="page-title">UK company analysis</h1>
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

          <ResultsPane tabs={companies.tabs} focusId={companies.focusId} />
        </div>
      </main>

      <SavedDrawer
        open={savedOpen}
        onClose={() => setSavedOpen(false)}
        onOpenItem={async (item) => {
          setSavedOpen(false);
          await companies.openSaved(item);
        }}
        reloadKey={savedReloadKey}
      />
    </div>
  );
}
