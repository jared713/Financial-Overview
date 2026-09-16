"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import type { Picked } from "@/components/CompanyRow";
import type { ResultTab } from "@/components/ResultsPane";
import { MAX_COMPANIES, MAX_FILINGS_PER_COMPANY, api } from "@/lib/api";
import type {
  CompanyAnalysis,
  CompanyHit,
  Comparison,
  FilingFeatures,
  IndustryAnalysis,
  SavedItem,
} from "@/lib/api";

const POLL_MS = 2500;

/** Both workspaces live here rather than in their pages, for two reasons:
 *  switching between Companies and Industries keeps everything you had set up,
 *  and a run started on one tab carries on polling while you work on the other. */
type Workspace = {
  features: FilingFeatures | null;
  error: string | null;
  setError: (message: string | null) => void;
  savedReloadKey: number;

  companies: {
    query: string;
    setQuery: (value: string) => void;
    hits: CompanyHit[] | null;
    searching: boolean;
    search: () => Promise<void>;
    clearSearch: () => void;
    picked: Picked[];
    add: (hit: CompanyHit) => Promise<void>;
    remove: (companyNumber: string) => void;
    toggleFiling: (companyNumber: string, transactionId: string) => void;
    toggleTradingName: (companyNumber: string) => void;
    setTradingName: (companyNumber: string, value: string) => void;
    analyse: (companyNumber: string) => Promise<void>;
    guidance: string;
    setGuidance: (value: string) => void;
    compare: () => Promise<void>;
    comparison: Comparison | null;
    tabs: ResultTab[];
    focusId: string | null;
    openSaved: (item: SavedItem) => Promise<void>;
    refine: (tab: ResultTab, instruction: string, files: File[]) => Promise<void>;
    deleteRevision: (tab: ResultTab, revisionId: string) => Promise<void>;
  };

  industry: {
    title: string;
    setTitle: (value: string) => void;
    prompt: string;
    setPrompt: (value: string) => void;
    files: File[];
    setFiles: (files: File[]) => void;
    uploading: boolean;
    run: () => Promise<void>;
    runs: IndustryAnalysis[];
    tabs: ResultTab[];
    focusId: string | null;
    openSaved: (item: SavedItem) => Promise<void>;
    refine: (tab: ResultTab, instruction: string, files: File[]) => Promise<void>;
    deleteRevision: (tab: ResultTab, revisionId: string) => Promise<void>;
  };
};

const WorkspaceContext = createContext<Workspace | null>(null);

export function useWorkspace(): Workspace {
  const context = useContext(WorkspaceContext);
  if (!context) throw new Error("useWorkspace must be used inside WorkspaceProvider");
  return context;
}

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const [features, setFeatures] = useState<FilingFeatures | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savedReloadKey, setSavedReloadKey] = useState(0);

  // Companies
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<CompanyHit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [picked, setPicked] = useState<Picked[]>([]);
  const [guidance, setGuidance] = useState("");
  const [comparison, setComparison] = useState<Comparison | null>(null);
  // Each thread is an analysis plus its revisions, oldest first.
  const [companyThreads, setCompanyThreads] = useState<CompanyAnalysis[][]>([]);
  const [companyFocusId, setCompanyFocusId] = useState<string | null>(null);

  // Industries
  const [title, setTitle] = useState("");
  const [prompt, setPrompt] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [industryThreads, setIndustryThreads] = useState<IndustryAnalysis[][]>([]);
  const [industryFocusId, setIndustryFocusId] = useState<string | null>(null);

  useEffect(() => {
    api.filingFeatures().then(setFeatures).catch(() => setFeatures(null));
  }, []);

  // Refs so the single polling timer always sees current state.
  const pickedRef = useRef<Picked[]>([]);
  const comparisonRef = useRef<Comparison | null>(null);
  const companyThreadsRef = useRef<CompanyAnalysis[][]>([]);
  const industryThreadsRef = useRef<IndustryAnalysis[][]>([]);
  useEffect(() => {
    pickedRef.current = picked;
  }, [picked]);
  useEffect(() => {
    comparisonRef.current = comparison;
  }, [comparison]);
  useEffect(() => {
    companyThreadsRef.current = companyThreads;
  }, [companyThreads]);
  useEffect(() => {
    industryThreadsRef.current = industryThreads;
  }, [industryThreads]);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
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
      let running = 0;
      try {
        for (const thread of companyThreadsRef.current) {
          for (const revision of thread) {
            if (revision.status !== "running") continue;
            running += 1;
            const next = await api.companyAnalysis(revision.id);
            setCompanyThreads((threads) =>
              threads.map((t) => t.map((r) => (r.id === next.id ? next : r))),
            );
            // The rail tracks the first analysis of each company.
            setPicked((list) =>
              list.map((item) =>
                item.analysis?.id === next.id ? { ...item, analysis: next } : item,
              ),
            );
          }
        }
        if (comparisonRef.current?.status === "running") {
          running += 1;
          setComparison(await api.comparison(comparisonRef.current.id));
        }
        for (const thread of industryThreadsRef.current) {
          for (const revision of thread) {
            if (revision.status !== "running") continue;
            running += 1;
            const next = await api.industry(revision.id);
            setIndustryThreads((threads) =>
              threads.map((t) => t.map((r) => (r.id === next.id ? next : r))),
            );
          }
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

  // --- Companies ----------------------------------------------------

  const search = useCallback(async () => {
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
  }, [query]);

  const clearSearch = useCallback(() => {
    setQuery("");
    setHits(null);
  }, []);

  const add = useCallback(
    async (hit: CompanyHit) => {
      let alreadyThere = false;
      setPicked((current) => {
        if (
          current.some((p) => p.profile.company_number === hit.company_number) ||
          current.length >= MAX_COMPANIES
        ) {
          alreadyThere = true;
          return current;
        }
        return [
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
        ];
      });
      if (alreadyThere) return;

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
    },
    [],
  );

  const remove = useCallback((companyNumber: string) => {
    setPicked((current) => current.filter((p) => p.profile.company_number !== companyNumber));
  }, []);

  const toggleFiling = useCallback((companyNumber: string, transactionId: string) => {
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
  }, []);

  const toggleTradingName = useCallback((companyNumber: string) => {
    setPicked((current) =>
      current.map((p) =>
        p.profile.company_number === companyNumber
          ? { ...p, tradingNameOn: !p.tradingNameOn }
          : p,
      ),
    );
  }, []);

  const setTradingName = useCallback((companyNumber: string, value: string) => {
    setPicked((current) =>
      current.map((p) =>
        p.profile.company_number === companyNumber ? { ...p, tradingName: value } : p,
      ),
    );
  }, []);

  const analyse = useCallback(
    async (companyNumber: string) => {
      const target = pickedRef.current.find(
        (p) => p.profile.company_number === companyNumber,
      );
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
        setCompanyThreads((threads) => [...threads, [analysis]]);
        setCompanyFocusId(analysis.id);
        ensurePolling();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [ensurePolling],
  );

  const compare = useCallback(async () => {
    const ids = pickedRef.current
      .filter((p) => p.analysis?.status === "done")
      .map((p) => p.analysis!.id);
    if (ids.length < 2) return;
    setError(null);
    try {
      const started = await api.compare(ids, guidance);
      setComparison(started);
      setCompanyFocusId(started.id);
      ensurePolling();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [ensurePolling, guidance]);

  const allCompanyTabs: ResultTab[] = [
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
    ...companyThreads
      .filter((thread) => thread.length > 0)
      .map((thread) => {
        const latest = thread[thread.length - 1];
        return {
          kind: "company" as const,
          id: thread[0].root_id,
          title: latest.company_name || latest.company_number,
          status: latest.status,
          revisions: thread,
        };
      }),
  ];

  const openSavedCompany = useCallback(
    async (item: SavedItem) => {
      setError(null);
      if (item.kind === "industry") {
        setError("That is an industry analysis — open it on the Industries page.");
        return;
      }
      setCompanyFocusId(item.id);
      try {
        if (item.kind === "analysis") {
          const thread = await api.companyThread(item.id);
          if (thread.length === 0) return;
          setCompanyThreads((threads) =>
            threads.some((t) => t[0]?.root_id === thread[0].root_id)
              ? threads
              : [...threads, thread],
          );
        } else {
          setComparison(await api.comparison(item.id));
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [],
  );

  // --- Industries ---------------------------------------------------

  const runIndustry = useCallback(async () => {
    if (!title.trim() || files.length === 0) return;
    setUploading(true);
    setError(null);
    try {
      const started = await api.analyseIndustry(title.trim(), prompt, files);
      setIndustryThreads((threads) => [...threads, [started]]);
      setIndustryFocusId(started.id);
      // The files are in the request now; clear them so the next run starts fresh.
      setFiles([]);
      ensurePolling();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  }, [ensurePolling, files, prompt, title]);

  const openSavedIndustry = useCallback(async (item: SavedItem) => {
    setError(null);
    if (item.kind !== "industry") {
      setError("That is a company analysis — open it on the Companies page.");
      return;
    }
    setIndustryFocusId(item.id);
    try {
      const thread = await api.industryThread(item.id);
      if (thread.length === 0) return;
      setIndustryThreads((threads) =>
        threads.some((t) => t[0]?.root_id === thread[0].root_id)
          ? threads
          : [...threads, thread],
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  const refineCompany = useCallback(
    async (tab: ResultTab, instruction: string) => {
      if (tab.kind !== "company") return;
      const latest = tab.revisions[tab.revisions.length - 1];
      setError(null);
      try {
        const revision = await api.refineCompany(latest.id, instruction);
        setCompanyThreads((threads) =>
          threads.map((t) =>
            t[0]?.root_id === revision.root_id ? [...t, revision] : t,
          ),
        );
        setCompanyFocusId(revision.id);
        ensurePolling();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [ensurePolling],
  );

  const refineIndustryRun = useCallback(
    async (tab: ResultTab, instruction: string, addedFiles: File[]) => {
      if (tab.kind !== "industry") return;
      const latest = tab.revisions[tab.revisions.length - 1];
      setError(null);
      try {
        const revision = await api.refineIndustry(latest.id, instruction, addedFiles);
        setIndustryThreads((threads) =>
          threads.map((t) =>
            t[0]?.root_id === revision.root_id ? [...t, revision] : t,
          ),
        );
        setIndustryFocusId(revision.id);
        ensurePolling();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [ensurePolling],
  );

  const deleteRevision = useCallback(async (tab: ResultTab, revisionId: string) => {
    setError(null);
    try {
      if (tab.kind === "company") {
        await api.deleteAnalysis(revisionId);
        setCompanyThreads((threads) =>
          threads
            .map((t) => t.filter((r) => r.id !== revisionId))
            .filter((t) => t.length > 0),
        );
        // The rail goes back to "Analyse" if its analysis was the one deleted.
        setPicked((list) =>
          list.map((item) =>
            item.analysis?.id === revisionId
              ? { ...item, analysis: undefined, analysedSelection: undefined }
              : item,
          ),
        );
      } else if (tab.kind === "industry") {
        await api.deleteIndustry(revisionId);
        setIndustryThreads((threads) =>
          threads
            .map((t) => t.filter((r) => r.id !== revisionId))
            .filter((t) => t.length > 0),
        );
      }
      setSavedReloadKey((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  const industryTabs: ResultTab[] = industryThreads
    .filter((thread) => thread.length > 0)
    .map((thread) => {
      const latest = thread[thread.length - 1];
      return {
        kind: "industry" as const,
        id: thread[0].root_id,
        title: latest.title,
        status: latest.status,
        revisions: thread,
      };
    });

  return (
    <WorkspaceContext.Provider
      value={{
        features,
        error,
        setError,
        savedReloadKey,
        companies: {
          query,
          setQuery,
          hits,
          searching,
          search,
          clearSearch,
          picked,
          add,
          remove,
          toggleFiling,
          toggleTradingName,
          setTradingName,
          analyse,
          guidance,
          setGuidance,
          compare,
          comparison,
          tabs: allCompanyTabs,
          focusId: companyFocusId,
          openSaved: openSavedCompany,
          refine: (tab, instruction) => refineCompany(tab, instruction),
          deleteRevision,
        },
        industry: {
          title,
          setTitle,
          prompt,
          setPrompt,
          files,
          setFiles,
          uploading,
          run: runIndustry,
          runs: industryThreads.flat(),
          tabs: industryTabs,
          focusId: industryFocusId,
          openSaved: openSavedIndustry,
          refine: refineIndustryRun,
          deleteRevision,
        },
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
}
