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

export function fmtBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
