"""Company analyses and comparisons, tracked as in-memory jobs.

Two units of work, deliberately separate:

  * A **company analysis** reads one company's chosen filings (and optionally
    the open web) and writes it up. You start these one at a time, as you build
    a list, and each takes a minute or two.
  * A **comparison** takes several finished analyses and writes them up against
    each other. It works from those write-ups rather than the PDFs, which is
    what keeps five companies inside one request.

Both are too slow to hold an HTTP request open, so each returns an id the client
polls.

State lives in this process only. A redeploy loses everything in flight and
anything finished (the client gets a 404 and re-runs), and a second replica would
not see the first one's work — so run this service as a single instance.
"""

from __future__ import annotations

import asyncio
import logging
import time

from app.config import Settings
from app.services.analysis_models import AnalysedFilingRef, CompanyAnalysis, Comparison
from app.services.companies_house import CompaniesHouseClient, CompaniesHouseError, Filing
from app.services.company_research import research_company
from app.services.filing_analysis import (
    FilingAnalysisError,
    analyse_filings,
    compare_companies,
)
from app.services.ownership import analyse_ownership
from app.services.store import get_store

log = logging.getLogger("financial-overview.analysis_jobs")

MAX_COMPANIES_PER_COMPARISON = 5
MAX_FILINGS_PER_COMPANY = 4
CACHE_TTL_SECONDS = 4 * 60 * 60


_analyses: dict[str, CompanyAnalysis] = {}
_comparisons: dict[str, Comparison] = {}


def _prune() -> None:
    """Drop old entries from the in-memory cache. Nothing is lost — finished runs
    are in the store, and get_analysis reads through to it."""
    cutoff = time.time() - CACHE_TTL_SECONDS
    for cache in (_analyses, _comparisons):
        for key, value in list(cache.items()):
            if value.created_at < cutoff:
                cache.pop(key, None)


def get_analysis(analysis_id: str) -> CompanyAnalysis | None:
    """In-flight runs live in memory; finished ones are read back from the store,
    so results outlive the process that produced them."""
    return _analyses.get(analysis_id) or get_store().get_analysis(analysis_id)


def get_comparison(comparison_id: str) -> Comparison | None:
    return _comparisons.get(comparison_id) or get_store().get_comparison(comparison_id)


def list_saved(limit: int = 200):
    return get_store().list_saved(limit)


def delete_analysis(analysis_id: str) -> bool:
    _analyses.pop(analysis_id, None)
    return get_store().delete_analysis(analysis_id)


def delete_comparison(comparison_id: str) -> bool:
    _comparisons.pop(comparison_id, None)
    return get_store().delete_comparison(comparison_id)


def _select_filings(all_filings: list[Filing], transaction_ids: list[str]) -> list[Filing]:
    by_id = {f.transaction_id: f for f in all_filings}
    missing = [t for t in transaction_ids if t not in by_id]
    if missing:
        raise CompaniesHouseError(f"No accounts filing found for: {', '.join(missing)}", 404)
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


async def _run_analysis(
    analysis: CompanyAnalysis,
    transaction_ids: list[str],
    trading_name: str | None,
    settings: Settings,
) -> None:
    try:
        client = CompaniesHouseClient(settings.companies_house_api_key or "")
        all_filings = await client.list_account_filings(analysis.company_number, limit=100)
        filings = _select_filings(all_filings, transaction_ids)
        profile = await client.get_company(analysis.company_number)
        analysis.company_name = profile.get("company_name") or analysis.company_number
        documents = await client.fetch_filing_documents(filings)
        analysis.filings = [
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
            company_name=analysis.company_name,
            company_number=analysis.company_number,
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
        )
        analysis.markdown = result.markdown
        analysis.model = result.model
        analysis.input_tokens += result.input_tokens or 0
        analysis.output_tokens += result.output_tokens or 0

        # Web research runs after the accounts review so it can be grounded in
        # the filed figures. Failing here does not fail the analysis.
        if analysis.research:
            try:
                research = await research_company(
                    company_name=analysis.company_name,
                    company_number=analysis.company_number,
                    trading_name=trading_name,
                    registered_office=_registered_office(profile),
                    sic_codes=[str(c) for c in (profile.get("sic_codes") or [])],
                    filings_review=result.markdown,
                    api_key=settings.anthropic_api_key,
                    model=settings.anthropic_model,
                )
                analysis.research_markdown = research.markdown
                analysis.input_tokens += research.input_tokens or 0
                analysis.output_tokens += research.output_tokens or 0
            except FilingAnalysisError as e:
                analysis.research_error = str(e)
            except Exception as e:
                log.exception("Research failed for %s", analysis.company_number)
                analysis.research_error = f"Unexpected error: {e}"

        # Ownership comes from a different corner of the Companies House record —
        # the PSC register plus confirmation statements — so it is its own pass.
        # Failing here does not fail the analysis.
        try:
            psc = await client.get_persons_with_significant_control(analysis.company_number)
            statements = await client.get_psc_statements(analysis.company_number)
            ownership_filings = await client.list_ownership_filings(analysis.company_number)
            ownership_documents = (
                await client.fetch_filing_documents(ownership_filings)
                if ownership_filings
                else []
            )
            ownership = await analyse_ownership(
                company_name=analysis.company_name,
                company_number=analysis.company_number,
                psc=psc,
                statements=statements,
                documents=ownership_documents,
                api_key=settings.anthropic_api_key,
                model=settings.anthropic_model,
            )
            analysis.ownership_markdown = ownership.markdown
            analysis.input_tokens += ownership.input_tokens or 0
            analysis.output_tokens += ownership.output_tokens or 0
        except (CompaniesHouseError, FilingAnalysisError) as e:
            analysis.ownership_error = str(e)
        except Exception as e:
            log.exception("Ownership review failed for %s", analysis.company_number)
            analysis.ownership_error = f"Unexpected error: {e}"

        analysis.status = "done"
    except (CompaniesHouseError, FilingAnalysisError) as e:
        analysis.status = "error"
        analysis.error = str(e)
    except Exception as e:
        log.exception("Analysis failed for %s", analysis.company_number)
        analysis.status = "error"
        analysis.error = f"Unexpected error: {e}"
    finally:
        try:
            get_store().save_analysis(analysis)
        except Exception:
            log.exception("Could not save analysis %s", analysis.id)


def start_analysis(
    *,
    company_number: str,
    transaction_ids: list[str],
    trading_name: str | None,
    research: bool,
    settings: Settings,
) -> CompanyAnalysis:
    _prune()
    analysis = CompanyAnalysis(company_number=company_number, research=research)
    _analyses[analysis.id] = analysis
    asyncio.create_task(_run_analysis(analysis, transaction_ids, trading_name, settings))
    return analysis


async def _run_comparison(
    comparison: Comparison, analyses: list[CompanyAnalysis], settings: Settings
) -> None:
    try:
        result = await compare_companies(
            [a.as_summary() for a in analyses],
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
            question=comparison.guidance,
            with_research=any(a.research_markdown for a in analyses),
        )
        comparison.markdown = result.markdown
        comparison.model = result.model
        comparison.input_tokens = result.input_tokens or 0
        comparison.output_tokens = result.output_tokens or 0
        comparison.status = "done"
    except FilingAnalysisError as e:
        comparison.status = "error"
        comparison.error = str(e)
    except Exception as e:
        log.exception("Comparison %s failed", comparison.id)
        comparison.status = "error"
        comparison.error = f"Unexpected error: {e}"
    finally:
        try:
            get_store().save_comparison(comparison)
        except Exception:
            log.exception("Could not save comparison %s", comparison.id)


def start_comparison(
    *, analyses: list[CompanyAnalysis], guidance: str | None, settings: Settings
) -> Comparison:
    _prune()
    comparison = Comparison(
        analysis_ids=[a.id for a in analyses],
        guidance=guidance,
        companies=[(a.company_number, a.company_name) for a in analyses],
    )
    _comparisons[comparison.id] = comparison
    asyncio.create_task(_run_comparison(comparison, analyses, settings))
    return comparison
