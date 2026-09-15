import logging

from fastapi import APIRouter, HTTPException, status

from app.config import Settings, get_settings
from app.schemas.companies import (
    AnalyseCompanyRequest,
    AnalysedFiling,
    CompanyAnalysisOut,
    ComparedCompany,
    CompareRequest,
    ComparisonOut,
    SavedItem,
)
from app.services.analysis_jobs import (
    delete_analysis,
    delete_comparison,
    get_analysis,
    get_comparison,
    list_saved,
    start_analysis,
    start_comparison,
)
from app.services.analysis_models import CompanyAnalysis, Comparison

log = logging.getLogger("financial-overview.analyses")

router = APIRouter(prefix="/analyses", tags=["analyses"])


def _require_keys(settings: Settings) -> None:
    if not settings.companies_house_api_key:
        raise HTTPException(503, "COMPANIES_HOUSE_API_KEY is not configured on the API service")
    if not settings.anthropic_api_key:
        raise HTTPException(
            503,
            "ANTHROPIC_API_KEY is not configured on the API service — filings can still "
            "be downloaded, but Claude review is unavailable",
        )


def _analysis_out(analysis: CompanyAnalysis) -> CompanyAnalysisOut:
    return CompanyAnalysisOut(
        id=analysis.id,
        status=analysis.status,
        company_number=analysis.company_number,
        company_name=analysis.company_name,
        research=analysis.research,
        filings=[
            AnalysedFiling(
                transaction_id=f.transaction_id,
                made_up_to=f.made_up_to,
                date=f.date,
                description=f.description,
                size_bytes=f.size_bytes,
            )
            for f in analysis.filings
        ],
        markdown=analysis.markdown,
        error=analysis.error,
        research_markdown=analysis.research_markdown,
        research_error=analysis.research_error,
        ownership_markdown=analysis.ownership_markdown,
        ownership_error=analysis.ownership_error,
        model=analysis.model,
        input_tokens=analysis.input_tokens,
        output_tokens=analysis.output_tokens,
    )


def _comparison_out(comparison: Comparison) -> ComparisonOut:
    return ComparisonOut(
        id=comparison.id,
        status=comparison.status,
        analysis_ids=comparison.analysis_ids,
        companies=[
            ComparedCompany(company_number=number, company_name=name)
            for number, name in comparison.companies
        ],
        markdown=comparison.markdown,
        error=comparison.error,
        model=comparison.model,
        input_tokens=comparison.input_tokens,
        output_tokens=comparison.output_tokens,
    )


@router.get("", response_model=list[SavedItem])
async def list_saved_work(limit: int = 200) -> list[SavedItem]:
    """Everything saved, newest first. Results are kept until deleted."""
    return [SavedItem(**item) for item in list_saved(limit)]


@router.post(
    "/company", response_model=CompanyAnalysisOut, status_code=status.HTTP_202_ACCEPTED
)
async def analyse_company(payload: AnalyseCompanyRequest) -> CompanyAnalysisOut:
    """Start one company's review; poll GET /analyses/company/{id} for it."""
    settings = get_settings()
    _require_keys(settings)
    analysis = start_analysis(
        company_number=payload.company_number,
        transaction_ids=payload.transaction_ids,
        trading_name=(payload.trading_name or "").strip() or None,
        research=payload.research,
        settings=settings,
    )
    log.info(
        "Started analysis %s for %s (research=%s)",
        analysis.id,
        payload.company_number,
        payload.research,
    )
    return _analysis_out(analysis)


@router.get("/company/{analysis_id}", response_model=CompanyAnalysisOut)
async def read_company_analysis(analysis_id: str) -> CompanyAnalysisOut:
    analysis = get_analysis(analysis_id)
    if analysis is None:
        raise HTTPException(
            404, "Analysis not found — it may have expired or the API restarted"
        )
    return _analysis_out(analysis)


@router.post(
    "/compare", response_model=ComparisonOut, status_code=status.HTTP_202_ACCEPTED
)
async def compare(payload: CompareRequest) -> ComparisonOut:
    """Compare finished company analyses; poll GET /analyses/compare/{id} for it."""
    settings = get_settings()
    _require_keys(settings)

    seen: set[str] = set()
    analyses: list[CompanyAnalysis] = []
    for analysis_id in payload.analysis_ids:
        if analysis_id in seen:
            raise HTTPException(400, "The same analysis was sent twice")
        seen.add(analysis_id)
        analysis = get_analysis(analysis_id)
        if analysis is None:
            raise HTTPException(
                404,
                f"Analysis {analysis_id} not found — it may have expired or the API "
                "restarted. Re-run that company.",
            )
        if analysis.status != "done":
            raise HTTPException(
                409,
                f"{analysis.company_name or analysis.company_number} has not finished "
                "being reviewed yet",
            )
        analyses.append(analysis)

    comparison = start_comparison(
        analyses=analyses, guidance=(payload.guidance or "").strip() or None, settings=settings
    )
    log.info("Started comparison %s across %d companies", comparison.id, len(analyses))
    return _comparison_out(comparison)


@router.get("/compare/{comparison_id}", response_model=ComparisonOut)
async def read_comparison(comparison_id: str) -> ComparisonOut:
    comparison = get_comparison(comparison_id)
    if comparison is None:
        raise HTTPException(
            404, "Comparison not found — it may have expired or the API restarted"
        )
    return _comparison_out(comparison)


@router.delete("/company/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company_analysis(analysis_id: str) -> None:
    if not delete_analysis(analysis_id):
        raise HTTPException(404, "Analysis not found")


@router.delete("/compare/{comparison_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saved_comparison(comparison_id: str) -> None:
    if not delete_comparison(comparison_id):
        raise HTTPException(404, "Comparison not found")
