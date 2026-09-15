"""Multi-company analysis runs, tracked as in-memory jobs.

A run can involve five companies and a couple of dozen PDFs, which takes minutes
— too long to hold an HTTP request open through Railway's proxy. So the request
starts a job and returns an id; the client polls and renders each company's
review as it lands.

State lives in this process only. A redeploy loses in-flight jobs (the client
gets a 404 and can start again), and a second replica would not see the first
one's jobs — so run this service as a single instance.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field

from app.config import Settings
from app.services.companies_house import CompaniesHouseClient, CompaniesHouseError, Filing
from app.services.company_research import research_company
from app.services.filing_analysis import (
    CompanySummary,
    FilingAnalysisError,
    analyse_filings,
    compare_companies,
)

log = logging.getLogger("financial-overview.analysis_jobs")

MAX_COMPANIES = 5
MAX_FILINGS_PER_COMPANY = 4
# Two companies at a time: enough to overlap the slow Claude calls without
# stacking concurrent Anthropic requests or hammering Companies House.
COMPANY_CONCURRENCY = 2
JOB_TTL_SECONDS = 2 * 60 * 60


@dataclass
class Selection:
    """One company as chosen in the UI."""

    company_number: str
    transaction_ids: list[str]
    # Companies trade under names that differ from the registered one far more
    # often than not; without it the web research finds the wrong business or
    # nothing at all.
    trading_name: str | None = None


@dataclass
class AnalysedFilingRef:
    transaction_id: str
    made_up_to: str | None = None
    date: str | None = None
    description: str | None = None
    size_bytes: int = 0


@dataclass
class CompanyRun:
    company_number: str
    company_name: str = ""
    status: str = "pending"  # pending | running | done | error
    filings: list[AnalysedFilingRef] = field(default_factory=list)
    markdown: str | None = None
    error: str | None = None
    research_markdown: str | None = None
    research_error: str | None = None


@dataclass
class AnalysisJob:
    id: str
    status: str = "running"  # running | done | error
    created_at: float = field(default_factory=time.time)
    question: str | None = None
    research: bool = False
    companies: list[CompanyRun] = field(default_factory=list)
    comparison_markdown: str | None = None
    comparison_error: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def finished_companies(self) -> int:
        return sum(1 for c in self.companies if c.status in ("done", "error"))


_jobs: dict[str, AnalysisJob] = {}


def _prune() -> None:
    cutoff = time.time() - JOB_TTL_SECONDS
    for job_id, job in list(_jobs.items()):
        if job.created_at < cutoff:
            _jobs.pop(job_id, None)


def get_job(job_id: str) -> AnalysisJob | None:
    return _jobs.get(job_id)


def create_job(
    selections: list[Selection], question: str | None, research: bool = False
) -> AnalysisJob:
    _prune()
    job = AnalysisJob(
        id=uuid.uuid4().hex,
        question=question,
        research=research,
        companies=[CompanyRun(company_number=s.company_number) for s in selections],
    )
    _jobs[job.id] = job
    return job


def _select_filings(all_filings: list[Filing], transaction_ids: list[str]) -> list[Filing]:
    by_id = {f.transaction_id: f for f in all_filings}
    missing = [t for t in transaction_ids if t not in by_id]
    if missing:
        raise CompaniesHouseError(
            f"No accounts filing found for: {', '.join(missing)}", 404
        )
    # Oldest first so a multi-year review reads forwards in time.
    return sorted((by_id[t] for t in transaction_ids), key=lambda f: f.date or "")


def _registered_office(profile: dict) -> str | None:
    address = profile.get("registered_office_address") or {}
    parts = [
        str(address[key])
        for key in ("address_line_1", "address_line_2", "locality", "region", "postal_code")
        if address.get(key)
    ]
    return ", ".join(parts) or None


async def _run_company(
    run: CompanyRun,
    selection: Selection,
    settings: Settings,
    question: str | None,
    job: AnalysisJob,
) -> CompanySummary | None:
    run.status = "running"
    try:
        client = CompaniesHouseClient(settings.companies_house_api_key or "")
        all_filings = await client.list_account_filings(run.company_number, limit=100)
        filings = _select_filings(all_filings, selection.transaction_ids)
        profile = await client.get_company(run.company_number)
        run.company_name = profile.get("company_name") or run.company_number
        documents = await client.fetch_filing_documents(filings)
        run.filings = [
            AnalysedFilingRef(
                transaction_id=d.filing.transaction_id,
                made_up_to=d.filing.made_up_to,
                date=d.filing.date,
                description=d.filing.description,
                size_bytes=len(d.content),
            )
            for d in documents
        ]

        result = await analyse_filings(
            documents,
            company_name=run.company_name,
            company_number=run.company_number,
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
            # The free-text question is answered once, in the comparison, so a
            # multi-company run does not repeat the same answer per company.
            question=question if len(job.companies) == 1 else None,
        )
        run.markdown = result.markdown
        job.model = result.model
        job.input_tokens += result.input_tokens or 0
        job.output_tokens += result.output_tokens or 0

        # Web research runs after the filings review so it can be grounded in the
        # filed figures. A failure here does not fail the company — the accounts
        # review stands on its own.
        if job.research:
            try:
                research = await research_company(
                    company_name=run.company_name,
                    company_number=run.company_number,
                    trading_name=selection.trading_name,
                    registered_office=_registered_office(profile),
                    sic_codes=[str(c) for c in (profile.get("sic_codes") or [])],
                    filings_review=result.markdown,
                    api_key=settings.anthropic_api_key,
                    model=settings.anthropic_model,
                )
                run.research_markdown = research.markdown
                job.input_tokens += research.input_tokens or 0
                job.output_tokens += research.output_tokens or 0
            except FilingAnalysisError as e:
                run.research_error = str(e)
            except Exception as e:
                log.exception("Research failed for %s", run.company_number)
                run.research_error = f"Unexpected error: {e}"

        run.status = "done"
        summary = result.markdown
        if run.research_markdown:
            summary = f"{summary}\n\n### Business and recent news\n\n{run.research_markdown}"
        return CompanySummary(
            company_number=run.company_number,
            company_name=run.company_name,
            markdown=summary,
        )
    except (CompaniesHouseError, FilingAnalysisError) as e:
        run.status = "error"
        run.error = str(e)
    except Exception as e:  # unexpected: surface it rather than hanging the job
        log.exception("Company run failed for %s", run.company_number)
        run.status = "error"
        run.error = f"Unexpected error: {e}"
    return None


async def run_job(
    job: AnalysisJob, selections: list[Selection], settings: Settings
) -> None:
    """Summarise each company concurrently, then compare the summaries."""
    semaphore = asyncio.Semaphore(COMPANY_CONCURRENCY)

    async def _one(run: CompanyRun, selection: Selection) -> CompanySummary | None:
        async with semaphore:
            return await _run_company(run, selection, settings, job.question, job)

    try:
        summaries = await asyncio.gather(
            *(
                _one(run, selection)
                for run, selection in zip(job.companies, selections, strict=True)
            )
        )
        done = [s for s in summaries if s is not None]

        if len(done) >= 2:
            try:
                comparison = await compare_companies(
                    done,
                    api_key=settings.anthropic_api_key,
                    model=settings.anthropic_model,
                    max_tokens=settings.anthropic_max_tokens,
                    question=job.question,
                    with_research=job.research,
                )
                job.comparison_markdown = comparison.markdown
                job.model = comparison.model
                job.input_tokens += comparison.input_tokens or 0
                job.output_tokens += comparison.output_tokens or 0
            except FilingAnalysisError as e:
                job.comparison_error = str(e)
        elif len(job.companies) > 1:
            job.comparison_error = (
                "Not enough companies were reviewed successfully to compare them"
            )

        job.status = "done" if done else "error"
    except Exception as e:  # pragma: no cover - defensive
        log.exception("Analysis job %s failed", job.id)
        job.status = "error"
        job.comparison_error = f"Unexpected error: {e}"


def start_job(
    selections: list[Selection],
    question: str | None,
    settings: Settings,
    research: bool = False,
) -> AnalysisJob:
    job = create_job(selections, question, research)
    asyncio.create_task(run_job(job, selections, settings))
    return job
