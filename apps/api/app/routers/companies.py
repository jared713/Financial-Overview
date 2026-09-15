import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.config import get_settings
from app.schemas.companies import (
    AnalysedFiling,
    AnalyseRequest,
    AnalysisOut,
    CompanyProfile,
    CompanySearchHit,
    FeatureStatus,
    FilingOut,
)
from app.services.companies_house import (
    CompaniesHouseClient,
    CompaniesHouseError,
    Filing,
)
from app.services.filing_analysis import FilingAnalysisError, analyse_filings
from app.services.store import get_store

log = logging.getLogger("financial-overview.companies")

router = APIRouter(prefix="/companies", tags=["companies"])


def _client() -> CompaniesHouseClient:
    settings = get_settings()
    try:
        return CompaniesHouseClient(settings.companies_house_api_key or "")
    except CompaniesHouseError as e:
        raise HTTPException(e.status_code, str(e)) from e


def _profile(data: dict) -> CompanyProfile:
    address = data.get("registered_office_address") or {}
    accounts = (data.get("accounts") or {})
    last_accounts = accounts.get("last_accounts") or {}
    next_accounts = accounts.get("next_accounts") or {}
    return CompanyProfile(
        company_number=str(data.get("company_number") or ""),
        company_name=data.get("company_name") or "",
        company_status=data.get("company_status"),
        company_type=data.get("type"),
        date_of_creation=data.get("date_of_creation"),
        registered_office=", ".join(
            str(address[k])
            for k in ("address_line_1", "address_line_2", "locality", "region", "postal_code")
            if address.get(k)
        )
        or None,
        sic_codes=[str(c) for c in (data.get("sic_codes") or [])],
        accounts_last_made_up_to=last_accounts.get("made_up_to"),
        accounts_next_due=next_accounts.get("due_on") or accounts.get("next_due"),
    )


def _filing_out(filing: Filing) -> FilingOut:
    return FilingOut(
        transaction_id=filing.transaction_id,
        date=filing.date,
        type=filing.type,
        description=filing.description,
        made_up_to=filing.made_up_to,
        paper_filed=filing.paper_filed,
        pages=filing.pages,
        downloadable=filing.document_id is not None,
    )


@router.get("/search", response_model=list[CompanySearchHit])
async def search_companies(
    q: str = Query(min_length=1, description="Company name or number"),
    limit: int = Query(20, ge=1, le=100),
) -> list[CompanySearchHit]:
    client = _client()
    try:
        hits = await client.search_companies(q, limit=limit)
    except CompaniesHouseError as e:
        raise HTTPException(e.status_code, str(e)) from e
    return [CompanySearchHit(**vars(hit)) for hit in hits]


@router.get("/features", response_model=FeatureStatus)
def feature_status() -> FeatureStatus:
    """What the deployment can actually do, so the UI can say why a button is off."""
    settings = get_settings()
    return FeatureStatus(
        companies_house=bool(settings.companies_house_api_key),
        claude_review=bool(settings.anthropic_api_key),
        model=settings.anthropic_model if settings.anthropic_api_key else None,
        saving_is_durable=get_store().durable,
    )


@router.get("/{company_number}", response_model=CompanyProfile)
async def get_company(company_number: str) -> CompanyProfile:
    client = _client()
    try:
        return _profile(await client.get_company(company_number))
    except CompaniesHouseError as e:
        raise HTTPException(e.status_code, str(e)) from e


@router.get("/{company_number}/filings", response_model=list[FilingOut])
async def list_filings(
    company_number: str, limit: int = Query(50, ge=1, le=100)
) -> list[FilingOut]:
    """Accounts filings only — the set that contains a balance sheet."""
    client = _client()
    try:
        filings = await client.list_account_filings(company_number, limit=limit)
    except CompaniesHouseError as e:
        raise HTTPException(e.status_code, str(e)) from e
    return [_filing_out(f) for f in filings]


async def _resolve_filings(
    client: CompaniesHouseClient, company_number: str, transaction_ids: list[str]
) -> list[Filing]:
    """Look transaction ids up in the filing history rather than trusting the
    caller's document id — keeps the document API reachable only for filings
    that really belong to this company."""
    filings = await client.list_account_filings(company_number, limit=100)
    by_id = {f.transaction_id: f for f in filings}
    missing = [t for t in transaction_ids if t not in by_id]
    if missing:
        raise HTTPException(
            404, f"No accounts filing on {company_number} for: {', '.join(missing)}"
        )
    return [by_id[t] for t in transaction_ids]


@router.get("/{company_number}/filings/{transaction_id}/pdf")
async def download_filing_pdf(company_number: str, transaction_id: str) -> Response:
    client = _client()
    try:
        filing = (await _resolve_filings(client, company_number, [transaction_id]))[0]
        documents = await client.fetch_filing_documents([filing])
    except CompaniesHouseError as e:
        raise HTTPException(e.status_code, str(e)) from e
    doc = documents[0]
    return Response(
        content=doc.content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{company_number}-{doc.filename}"',
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.post("/{company_number}/analyse", response_model=AnalysisOut)
async def analyse_company_filings(company_number: str, payload: AnalyseRequest) -> AnalysisOut:
    """Pull the selected account PDFs and have Claude summarise / compare them."""
    settings = get_settings()
    client = _client()
    try:
        filings = await _resolve_filings(client, company_number, payload.transaction_ids)
        profile = _profile(await client.get_company(company_number))
        documents = await client.fetch_filing_documents(filings)
    except CompaniesHouseError as e:
        raise HTTPException(e.status_code, str(e)) from e

    try:
        result = await analyse_filings(
            documents,
            company_name=profile.company_name or company_number,
            company_number=company_number,
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
            question=payload.question,
        )
    except FilingAnalysisError as e:
        raise HTTPException(e.status_code, str(e)) from e

    return AnalysisOut(
        company_number=company_number,
        company_name=profile.company_name,
        filings=[
            AnalysedFiling(
                transaction_id=d.filing.transaction_id,
                made_up_to=d.filing.made_up_to,
                date=d.filing.date,
                description=d.filing.description,
                size_bytes=len(d.content),
            )
            for d in documents
        ],
        markdown=result.markdown,
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
