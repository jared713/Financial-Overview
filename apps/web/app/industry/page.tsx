"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Banner } from "@/components/Banner";
import { IndustryRail } from "@/components/IndustryRail";
import { ResultsPane } from "@/components/ResultsPane";
import type { ResultTab } from "@/components/ResultsPane";
import { SavedDrawer } from "@/components/SavedDrawer";
import { api } from "@/lib/api";
import type { FilingFeatures, IndustryAnalysis, SavedItem } from "@/lib/api";

const POLL_MS = 2500;

export default function IndustryPage() {
  const [features, setFeatures] = useState<FilingFeatures | null>(null);

  const [title, setTitle] = useState("");
  const [prompt, setPrompt] = useState("");
  const [files, setFiles] = useState<File[]>([]);

  const [runs, setRuns] = useState<IndustryAnalysis[]>([]);
  const [focusId, setFocusId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [savedOpen, setSavedOpen] = useState(false);
  const [savedReloadKey, setSavedReloadKey] = useState(0);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const runsRef = useRef<IndustryAnalysis[]>([]);
  useEffect(() => {
    runsRef.current = runs;
  }, [runs]);

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

  const ensurePolling = useCallback(() => {
    if (pollRef.current) return;
    pollRef.current = setInterval(async () => {
      const running = runsRef.current.filter((r) => r.status === "running");
      if (running.length === 0) {
        stopPolling();
        setSavedReloadKey((n) => n + 1);
        return;
      }
      try {
        for (const run of running) {
          const next = await api.industry(run.id);
          setRuns((list) => list.map((r) => (r.id === next.id ? next : r)));
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        stopPolling();
      }
    }, POLL_MS);
  }, [stopPolling]);

  async function run() {
    if (!title.trim() || files.length === 0) return;
    setUploading(true);
    setError(null);
    try {
      const started = await api.analyseIndustry(title.trim(), prompt, files);
      setRuns((current) => [...current, started]);
      setFocusId(started.id);
      // The files are in the request now; clear them so the next run starts fresh.
      setFiles([]);
      ensurePolling();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  }

  async function openSavedItem(item: SavedItem) {
    setSavedOpen(false);
    setError(null);
    if (runs.some((r) => r.id === item.id)) {
      setFocusId(item.id);
      return;
    }
    if (item.kind !== "industry") {
      setError("That is a company analysis — open it on the Companies page.");
      return;
    }
    try {
      const loaded = await api.industry(item.id);
      setRuns((current) => [...current, loaded]);
      setFocusId(loaded.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const claudeOff = features !== null && !features.claude_review;
  const tabs: ResultTab[] = runs.map((industry) => ({
    kind: "industry" as const,
    id: industry.id,
    title: industry.title,
    status: industry.status,
    industry,
  }));

  return (
    <div className="lg:grid lg:grid-cols-[22rem_minmax(0,1fr)]">
      <aside className="border-b border-line bg-surface lg:sticky lg:top-14 lg:h-[calc(100vh-3.5rem)] lg:overflow-hidden lg:border-b-0 lg:border-r">
        <IndustryRail
          title={title}
          onTitleChange={setTitle}
          prompt={prompt}
          onPromptChange={setPrompt}
          files={files}
          onFilesChange={setFiles}
          onRun={run}
          busy={uploading || runs.some((r) => r.status === "running")}
          disabled={claudeOff}
        />
      </aside>

      <main className="min-w-0 space-y-4 px-5 py-6 sm:px-8">
        <div className="mx-auto w-full max-w-5xl space-y-4">
          <header className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="page-title">Industry analysis</h1>
              <p className="page-subtitle">
                Upload what you have — market reviews, policy papers, surveys — and say
                what you want out of them.
              </p>
            </div>
            <button type="button" onClick={() => setSavedOpen(true)} className="btn-secondary">
              Saved
            </button>
          </header>

          {claudeOff && (
            <Banner tone="amber">
              <code className="font-mono text-xs">ANTHROPIC_API_KEY</code> is not set on
              the API service, so documents cannot be analysed.
            </Banner>
          )}
          {features?.saving_is_durable === false && (
            <Banner tone="amber">
              Results are being saved, but the API has no volume mounted, so they will be
              lost on the next deploy.
            </Banner>
          )}
          {error && <Banner tone="red">{error}</Banner>}

          <ResultsPane tabs={tabs} focusId={focusId} empty={<IndustryEmptyState />} />
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

function IndustryEmptyState() {
  return (
    <div className="card card-body">
      <h2 className="text-base font-semibold text-ink">Nothing analysed yet</h2>
      <p className="mt-1 text-sm text-muted">
        This side is separate from company analysis — it reads only the documents you
        give it.
      </p>
      <ol className="mt-4 space-y-3">
        {[
          ["Name the industry", "So the write-up knows what it is about — e.g. UK EdTech."],
          [
            "Upload the documents",
            "Government reviews, regulator reports, trade surveys. PDF or plain text.",
          ],
          [
            "Say what you want",
            "A market sizing, a policy read, a list of the players. Leave it blank for a general summary.",
          ],
        ].map(([heading, body], i) => (
          <li key={heading} className="flex gap-3">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold text-accent">
              {i + 1}
            </span>
            <span className="text-sm">
              <span className="font-medium text-ink">{heading}</span>
              <span className="block text-muted">{body}</span>
            </span>
          </li>
        ))}
      </ol>
      <p className="mt-5 border-t border-line pt-4 text-xs text-subtle">
        Claude is told to attribute every figure to the document it came from, to separate
        what a document states from what it is inferring, and to say what the documents do
        not cover. Uploaded files are read into the request and not stored — only the
        write-up is kept.
      </p>
    </div>
  );
}
