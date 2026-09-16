export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type CompanyHit = {
  company_number: string;
  title: string;
  company_status?: string | null;
  company_type?: string | null;
  date_of_creation?: string | null;
  address_snippet?: string | null;
};

export type CompanyProfile = {
  company_number: string;
  company_name: string;
  company_status?: string | null;
  company_type?: string | null;
  date_of_creation?: string | null;
  registered_office?: string | null;
  sic_codes: string[];
  accounts_last_made_up_to?: string | null;
  accounts_next_due?: string | null;
};

export type Filing = {
  transaction_id: string;
  date?: string | null;
  type?: string | null;
  description?: string | null;
  made_up_to?: string | null;
  paper_filed: boolean;
  pages?: number | null;
  downloadable: boolean;
};

export type FilingFeatures = {
  companies_house: boolean;
  claude_review: boolean;
  model?: string | null;
  /** False when the API has no volume, so saved work is lost on redeploy. */
  saving_is_durable: boolean;
};

export type IndustryDocument = { filename: string; size_bytes: number };

export type IndustryAnalysis = Threaded & {
  id: string;
  status: RunStatus;
  title: string;
  prompt?: string | null;
  documents: IndustryDocument[];
  markdown?: string | null;
  error?: string | null;
  model?: string | null;
  input_tokens: number;
  output_tokens: number;
};

export type SavedItem = {
  kind: "analysis" | "comparison" | "industry";
  id: string;
  created_at: number;
  title: string;
  subtitle: string;
  status: RunStatus;
  research: boolean;
  revisions: number;
};

export const MAX_COMPANIES = 5;
export const MAX_FILINGS_PER_COMPANY = 4;

export type AnalysedFiling = {
  transaction_id: string;
  made_up_to?: string | null;
  date?: string | null;
  description?: string | null;
  size_bytes: number;
};

export type RunStatus = "running" | "done" | "error";

type Threaded = {
  /** Set on a revision; null on the first analysis in a thread. */
  parent_id?: string | null;
  /** The id of the first analysis in the thread — the key for the whole chain. */
  root_id: string;
  /** What was asked for in this revision. */
  instruction?: string | null;
  created_at: number;
};

export type CompanyAnalysis = Threaded & {
  id: string;
  status: RunStatus;
  company_number: string;
  company_name: string;
  research: boolean;
  filings: AnalysedFiling[];
  markdown?: string | null;
  error?: string | null;
  research_markdown?: string | null;
  research_error?: string | null;
  ownership_markdown?: string | null;
  ownership_error?: string | null;
  model?: string | null;
  input_tokens: number;
  output_tokens: number;
};

export type Comparison = {
  id: string;
  status: RunStatus;
  analysis_ids: string[];
  companies: { company_number: string; company_name: string }[];
  markdown?: string | null;
  error?: string | null;
  model?: string | null;
  input_tokens: number;
  output_tokens: number;
};

export type FilingAnalysis = {
  company_number: string;
  company_name: string;
  filings: {
    transaction_id: string;
    made_up_to?: string | null;
    date?: string | null;
    description?: string | null;
    size_bytes: number;
  }[];
  markdown: string;
  model: string;
  input_tokens?: number | null;
  output_tokens?: number | null;
};

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    // Surface the API's own detail — Companies House failures (missing key,
    // rate limit) are explained in the body.
    const detail = await res
      .json()
      .then((b) => (typeof b?.detail === "string" ? b.detail : null))
      .catch(() => null);
    throw new Error(detail ?? `API ${path} -> ${res.status} ${res.statusText}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  filingFeatures: () => apiFetch<FilingFeatures>("/companies/features"),
  searchCompanies: (q: string) =>
    apiFetch<CompanyHit[]>(`/companies/search?q=${encodeURIComponent(q)}`),
  company: (companyNumber: string) =>
    apiFetch<CompanyProfile>(`/companies/${companyNumber}`),
  companyFilings: (companyNumber: string) =>
    apiFetch<Filing[]>(`/companies/${companyNumber}/filings`),
  analyseCompany: (body: {
    company_number: string;
    transaction_ids: string[];
    trading_name?: string | null;
    research?: boolean;
  }) =>
    apiFetch<CompanyAnalysis>("/analyses/company", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  companyAnalysis: (id: string) => apiFetch<CompanyAnalysis>(`/analyses/company/${id}`),
  companyThread: (id: string) =>
    apiFetch<CompanyAnalysis[]>(`/analyses/company/${id}/thread`),
  refineCompany: (id: string, instruction: string) =>
    apiFetch<CompanyAnalysis>(`/analyses/company/${id}/refine`, {
      method: "POST",
      body: JSON.stringify({ instruction }),
    }),
  compare: (analysisIds: string[], guidance?: string) =>
    apiFetch<Comparison>("/analyses/compare", {
      method: "POST",
      body: JSON.stringify({
        analysis_ids: analysisIds,
        guidance: guidance?.trim() ? guidance.trim() : null,
      }),
    }),
  comparison: (id: string) => apiFetch<Comparison>(`/analyses/compare/${id}`),

  /** Multipart, so this one cannot go through apiFetch — the browser has to set
   *  its own Content-Type with the boundary. */
  analyseIndustry: async (
    title: string,
    prompt: string,
    files: File[],
  ): Promise<IndustryAnalysis> => {
    const form = new FormData();
    form.append("title", title);
    if (prompt.trim()) form.append("prompt", prompt.trim());
    for (const file of files) form.append("files", file);
    const res = await fetch(`${API_URL}/industry`, { method: "POST", body: form });
    if (!res.ok) {
      const detail = await res
        .json()
        .then((b) => (typeof b?.detail === "string" ? b.detail : null))
        .catch(() => null);
      throw new Error(detail ?? `Upload failed: ${res.status} ${res.statusText}`);
    }
    return res.json();
  },
  industry: (id: string) => apiFetch<IndustryAnalysis>(`/industry/${id}`),
  industryThread: (id: string) =>
    apiFetch<IndustryAnalysis[]>(`/industry/${id}/thread`),
  refineIndustry: async (
    id: string,
    instruction: string,
    files: File[],
  ): Promise<IndustryAnalysis> => {
    const form = new FormData();
    form.append("instruction", instruction);
    for (const file of files) form.append("files", file);
    const res = await fetch(`${API_URL}/industry/${id}/refine`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      const detail = await res
        .json()
        .then((b) => (typeof b?.detail === "string" ? b.detail : null))
        .catch(() => null);
      throw new Error(detail ?? `Revision failed: ${res.status} ${res.statusText}`);
    }
    return res.json();
  },
  deleteIndustry: (id: string) =>
    apiFetch<void>(`/industry/${id}`, { method: "DELETE" }),

  saved: () => apiFetch<SavedItem[]>("/analyses"),
  deleteAnalysis: (id: string) =>
    apiFetch<void>(`/analyses/company/${id}`, { method: "DELETE" }),
  deleteComparison: (id: string) =>
    apiFetch<void>(`/analyses/compare/${id}`, { method: "DELETE" }),

  analyseFilings: (
    companyNumber: string,
    transactionIds: string[],
    question?: string,
  ) =>
    apiFetch<FilingAnalysis>(`/companies/${companyNumber}/analyse`, {
      method: "POST",
      body: JSON.stringify({
        transaction_ids: transactionIds,
        question: question?.trim() ? question.trim() : null,
      }),
    }),
};

/** Direct link to the filing PDF, proxied by the API (Companies House needs an API key). */
export function filingPdfUrl(companyNumber: string, transactionId: string): string {
  return `${API_URL}/companies/${companyNumber}/filings/${transactionId}/pdf`;
}

/** Input price per million tokens, for the rough pre-flight cost estimate.
 *  Keep in step with the model set in ANTHROPIC_MODEL on the API. */
const INPUT_PRICE_PER_MTOK: Record<string, number> = {
  "claude-opus-5": 5,
  "claude-sonnet-5": 2,
  "claude-haiku-4-5": 1,
};

/** A filing page costs roughly 1.5k-3k tokens once rendered as text + image. */
const TOKENS_PER_PAGE = 2200;

export function estimateCost(pages: number, model?: string | null): string | null {
  const price = INPUT_PRICE_PER_MTOK[model ?? "claude-opus-5"];
  if (!price || pages <= 0) return null;
  const dollars = (pages * TOKENS_PER_PAGE * price) / 1_000_000;
  if (dollars < 0.1) return "under $0.10";
  return `~$${dollars.toFixed(dollars < 10 ? 2 : 0)}`;
}

export function fmtWhen(epochSeconds: number): string {
  const date = new Date(epochSeconds * 1000);
  const days = (Date.now() - date.getTime()) / 86_400_000;
  if (days < 1) {
    return date.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  }
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

export function fmtBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
