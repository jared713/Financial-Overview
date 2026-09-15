"""Companies House REST client.

Three endpoints matter for pulling account filings:

  1. GET  api.company-information.service.gov.uk/search/companies?q=...
     Free-text company search -> company numbers.
  2. GET  api.company-information.service.gov.uk/company/{number}/filing-history?category=accounts
     Filing history, filtered to accounts. Each item carries a
     `links.document_metadata` URL on the *document* API.
  3. GET  document-api.company-information.service.gov.uk/document/{id}/content
     with `Accept: application/pdf`. This answers 302 to a signed AWS S3 URL.
     The Authorization header must NOT be replayed to S3 — the signed URL
     carries its own credentials and S3 rejects two auth mechanisms — so the
     redirect is followed by hand with a clean client.

Auth is HTTP Basic: API key as the username, empty password.

Docs: https://developer.company-information.service.gov.uk/
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

log = logging.getLogger("financial-overview.companies_house")

PUBLIC_API = "https://api.company-information.service.gov.uk"
DOCUMENT_API = "https://document-api.company-information.service.gov.uk"

# Filing-history categories. Accounts carry the numbers; confirmation statements
# carry the shareholder list (in full every third year, changes in between) and
# capital filings carry share allotments and statements of capital.
ACCOUNTS_CATEGORY = "accounts"
CONFIRMATION_CATEGORY = "confirmation-statement"
CAPITAL_CATEGORY = "capital"

MAX_PDF_BYTES = 30 * 1024 * 1024


class CompaniesHouseError(RuntimeError):
    """Any non-recoverable failure talking to Companies House."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class CompanyHit:
    company_number: str
    title: str
    company_status: str | None = None
    company_type: str | None = None
    date_of_creation: str | None = None
    address_snippet: str | None = None


@dataclass
class Filing:
    transaction_id: str
    date: str | None
    type: str | None
    description: str | None
    made_up_to: str | None
    paper_filed: bool = False
    pages: int | None = None
    document_id: str | None = None


@dataclass
class FilingDocument:
    filing: Filing
    content: bytes
    content_type: str = "application/pdf"

    @property
    def filename(self) -> str:
        stem = self.filing.made_up_to or self.filing.date or self.filing.transaction_id
        return f"accounts-{stem}.pdf"


@dataclass
class _CacheEntry:
    value: bytes
    expires_at: float


@dataclass
class _DocumentCache:
    """Small TTL cache so downloading then analysing a filing costs one fetch.

    Bounded by total bytes; oldest entries are dropped first. Process-local and
    deliberately unsophisticated — it is a courtesy to the Companies House rate
    limit (600 requests / 5 minutes), not a durable store.
    """

    ttl_seconds: float = 30 * 60
    max_bytes: int = 256 * 1024 * 1024
    _entries: dict[str, _CacheEntry] = field(default_factory=dict)

    def get(self, key: str) -> bytes | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at < time.monotonic():
            self._entries.pop(key, None)
            return None
        return entry.value

    def put(self, key: str, value: bytes) -> None:
        if len(value) > self.max_bytes:
            return
        self._entries[key] = _CacheEntry(value=value, expires_at=time.monotonic() + self.ttl_seconds)
        self._evict()

    def _evict(self) -> None:
        now = time.monotonic()
        for key, entry in list(self._entries.items()):
            if entry.expires_at < now:
                self._entries.pop(key, None)
        total = sum(len(e.value) for e in self._entries.values())
        while total > self.max_bytes and self._entries:
            oldest = min(self._entries, key=lambda k: self._entries[k].expires_at)
            total -= len(self._entries.pop(oldest).value)


_document_cache = _DocumentCache()


def document_id_from_metadata_url(url: str | None) -> str | None:
    """`https://document-api…/document/ABC-123` -> `ABC-123`."""
    if not url:
        return None
    return url.rstrip("/").rsplit("/", 1)[-1] or None


def parse_company_hit(item: dict[str, Any]) -> CompanyHit:
    return CompanyHit(
        company_number=str(item.get("company_number") or ""),
        title=item.get("title") or "",
        company_status=item.get("company_status"),
        company_type=item.get("company_type"),
        date_of_creation=item.get("date_of_creation"),
        address_snippet=item.get("address_snippet"),
    )


def parse_filing(item: dict[str, Any]) -> Filing:
    """Normalise one filing-history item.

    `description_values.made_up_date` is the period end date for accounts and is
    what humans actually compare on, so it is lifted out of the nested blob.
    """
    values = item.get("description_values") or {}
    return Filing(
        transaction_id=str(item.get("transaction_id") or ""),
        date=item.get("date"),
        type=item.get("type"),
        description=item.get("description"),
        made_up_to=values.get("made_up_date") or values.get("made_up_to"),
        paper_filed=bool(item.get("paper_filed")),
        pages=item.get("pages"),
        document_id=document_id_from_metadata_url(
            (item.get("links") or {}).get("document_metadata")
        ),
    )


class CompaniesHouseClient:
    def __init__(self, api_key: str, *, timeout: float = 60.0):
        if not api_key:
            raise CompaniesHouseError(
                "COMPANIES_HOUSE_API_KEY is not configured on the API service", 503
            )
        self._auth = httpx.BasicAuth(api_key, "")
        self._timeout = timeout

    async def _get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout, auth=self._auth) as client:
            resp = await client.get(url, params=params)
        if resp.status_code == 401:
            raise CompaniesHouseError("Companies House rejected the API key (401)", 502)
        if resp.status_code == 404:
            raise CompaniesHouseError("Not found at Companies House", 404)
        if resp.status_code == 429:
            raise CompaniesHouseError(
                "Companies House rate limit hit (600 requests / 5 min) — try again shortly", 429
            )
        if resp.status_code >= 400:
            raise CompaniesHouseError(
                f"Companies House returned {resp.status_code} for {url}", 502
            )
        return resp.json()

    async def search_companies(self, query: str, *, limit: int = 20) -> list[CompanyHit]:
        data = await self._get_json(
            f"{PUBLIC_API}/search/companies", {"q": query, "items_per_page": limit}
        )
        return [parse_company_hit(item) for item in data.get("items") or []]

    async def get_company(self, company_number: str) -> dict[str, Any]:
        return await self._get_json(f"{PUBLIC_API}/company/{company_number}")

    async def list_filings(
        self, company_number: str, category: str, *, limit: int = 50
    ) -> list[Filing]:
        data = await self._get_json(
            f"{PUBLIC_API}/company/{company_number}/filing-history",
            {"category": category, "items_per_page": limit},
        )
        filings = [parse_filing(item) for item in data.get("items") or []]
        # Newest first — Companies House already sorts this way, but paper and
        # electronic filings have been observed interleaved out of order.
        return sorted(filings, key=lambda f: f.date or "", reverse=True)

    async def list_account_filings(
        self, company_number: str, *, limit: int = 50
    ) -> list[Filing]:
        return await self.list_filings(company_number, ACCOUNTS_CATEGORY, limit=limit)

    async def list_ownership_filings(self, company_number: str) -> list[Filing]:
        """The filings that name shareholders: recent confirmation statements
        first, then capital filings (allotments, statements of capital)."""
        confirmations = await self.list_filings(
            company_number, CONFIRMATION_CATEGORY, limit=10
        )
        capital = await self.list_filings(company_number, CAPITAL_CATEGORY, limit=10)
        downloadable = [f for f in confirmations if f.document_id][:2]
        downloadable += [f for f in capital if f.document_id][:2]
        return downloadable

    async def get_persons_with_significant_control(
        self, company_number: str
    ) -> dict[str, Any]:
        """PSC register: who owns or controls more than 25%.

        A company with nothing registered answers 404 rather than an empty list,
        and listed companies are exempt entirely — both are normal, so this
        returns an empty result instead of raising.
        """
        try:
            return await self._get_json(
                f"{PUBLIC_API}/company/{company_number}/persons-with-significant-control",
                {"items_per_page": 50},
            )
        except CompaniesHouseError as e:
            if e.status_code == 404:
                return {"items": [], "total_results": 0}
            raise

    async def get_psc_statements(self, company_number: str) -> dict[str, Any]:
        """Why a company has no PSC listed — exempt, still investigating, and so on."""
        try:
            return await self._get_json(
                f"{PUBLIC_API}/company/{company_number}"
                "/persons-with-significant-control-statements",
                {"items_per_page": 20},
            )
        except CompaniesHouseError as e:
            if e.status_code == 404:
                return {"items": []}
            raise

    async def fetch_document_pdf(self, document_id: str) -> bytes:
        """Download one filing as PDF bytes, following the S3 redirect by hand."""
        cached = _document_cache.get(document_id)
        if cached is not None:
            return cached

        async with httpx.AsyncClient(timeout=self._timeout, auth=self._auth) as client:
            resp = await client.get(
                f"{DOCUMENT_API}/document/{document_id}/content",
                headers={"Accept": "application/pdf"},
                follow_redirects=False,
            )

        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("location")
            if not location:
                raise CompaniesHouseError("Document redirect carried no Location header", 502)
            # No auth here: the signed URL carries its own credentials and S3
            # rejects a request presenting two auth mechanisms.
            async with httpx.AsyncClient(timeout=self._timeout) as plain:
                resp = await plain.get(location, follow_redirects=True)
        if resp.status_code == 404:
            raise CompaniesHouseError("Filing document not available for download", 404)
        if resp.status_code >= 400:
            raise CompaniesHouseError(
                f"Document download failed with {resp.status_code}", 502
            )

        content = resp.content
        if not content:
            raise CompaniesHouseError("Filing document was empty", 502)
        if len(content) > MAX_PDF_BYTES:
            raise CompaniesHouseError(
                f"Filing PDF is {len(content) // (1024 * 1024)}MB, over the "
                f"{MAX_PDF_BYTES // (1024 * 1024)}MB limit",
                413,
            )
        _document_cache.put(document_id, content)
        return content

    async def fetch_filing_documents(self, filings: list[Filing]) -> list[FilingDocument]:
        """Download several filings concurrently, preserving input order."""
        missing = [f.transaction_id for f in filings if not f.document_id]
        if missing:
            raise CompaniesHouseError(
                f"No downloadable document for filing(s): {', '.join(missing)}", 404
            )

        semaphore = asyncio.Semaphore(4)

        async def _one(filing: Filing) -> FilingDocument:
            async with semaphore:
                assert filing.document_id is not None
                content = await self.fetch_document_pdf(filing.document_id)
            return FilingDocument(filing=filing, content=content)

        return list(await asyncio.gather(*(_one(f) for f in filings)))
