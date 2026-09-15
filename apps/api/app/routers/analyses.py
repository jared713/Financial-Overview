import logging

from fastapi import APIRouter, HTTPException, status

from app.config import get_settings
from app.schemas.companies import (
    AnalysedFiling,
    AnalysisJobOut,
    AnalysisRequest,
    CompanyRunOut,
)
from app.services.analysis_jobs import AnalysisJob, get_job, start_job

log = logging.getLogger("financial-overview.analyses")

router = APIRouter(prefix="/analyses", tags=["analyses"])


def _out(job: AnalysisJob) -> AnalysisJobOut:
    return AnalysisJobOut(
        id=job.id,
        status=job.status,
        companies=[
            CompanyRunOut(
                company_number=run.company_number,
                company_name=run.company_name,
                status=run.status,
                filings=[
                    AnalysedFiling(
                        transaction_id=f.transaction_id,
                        made_up_to=f.made_up_to,
                        date=f.date,
                        description=f.description,
                        size_bytes=f.size_bytes,
                    )
                    for f in run.filings
                ],
                markdown=run.markdown,
                error=run.error,
            )
            for run in job.companies
        ],
        finished=job.finished_companies,
        total=len(job.companies),
        comparison_markdown=job.comparison_markdown,
        comparison_error=job.comparison_error,
        model=job.model,
        input_tokens=job.input_tokens,
        output_tokens=job.output_tokens,
    )


@router.post("", response_model=AnalysisJobOut, status_code=status.HTTP_202_ACCEPTED)
async def start_analysis(payload: AnalysisRequest) -> AnalysisJobOut:
    """Kick off a review of one or more companies; poll GET /analyses/{id} for it.

    Each company is summarised from its own filings, then — with two or more —
    the summaries are compared.
    """
    settings = get_settings()
    if not settings.companies_house_api_key:
        raise HTTPException(503, "COMPANIES_HOUSE_API_KEY is not configured on the API service")
    if not settings.anthropic_api_key:
        raise HTTPException(
            503,
            "ANTHROPIC_API_KEY is not configured on the API service — filings can still "
            "be downloaded, but Claude review is unavailable",
        )

    seen: set[str] = set()
    selections: list[tuple[str, list[str]]] = []
    for item in payload.companies:
        if item.company_number in seen:
            raise HTTPException(400, f"Company {item.company_number} selected twice")
        seen.add(item.company_number)
        selections.append((item.company_number, item.transaction_ids))

    job = start_job(selections, payload.question, settings)
    log.info("Started analysis %s for %d companies", job.id, len(selections))
    return _out(job)


@router.get("/{job_id}", response_model=AnalysisJobOut)
async def read_analysis(job_id: str) -> AnalysisJobOut:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(404, "Analysis not found — it may have expired or the API restarted")
    return _out(job)
