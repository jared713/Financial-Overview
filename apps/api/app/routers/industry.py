import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.config import get_settings
from app.schemas.companies import IndustryAnalysisOut, IndustryDocumentOut
from app.services.analysis_jobs import (
    delete_industry,
    get_industry,
    start_industry_analysis,
)
from app.services.analysis_models import IndustryAnalysis
from app.services.filing_analysis import FilingAnalysisError
from app.services.industry import MAX_FILES, UploadedDocument, validate_documents

log = logging.getLogger("financial-overview.industry")

router = APIRouter(prefix="/industry", tags=["industry"])


def _out(analysis: IndustryAnalysis) -> IndustryAnalysisOut:
    return IndustryAnalysisOut(
        id=analysis.id,
        status=analysis.status,
        title=analysis.title,
        prompt=analysis.prompt,
        documents=[
            IndustryDocumentOut(filename=d.filename, size_bytes=d.size_bytes)
            for d in analysis.documents
        ],
        markdown=analysis.markdown,
        error=analysis.error,
        model=analysis.model,
        input_tokens=analysis.input_tokens,
        output_tokens=analysis.output_tokens,
    )


@router.post("", response_model=IndustryAnalysisOut, status_code=status.HTTP_202_ACCEPTED)
async def start_industry(
    title: str = Form(...),
    prompt: str | None = Form(None),
    files: list[UploadFile] = File(...),
) -> IndustryAnalysisOut:
    """Analyse uploaded documents about an industry; poll GET /industry/{id}.

    The files are read into the request to Claude and then dropped — only the
    filenames and the resulting write-up are stored.
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise HTTPException(503, "ANTHROPIC_API_KEY is not configured on the API service")
    if not title.strip():
        raise HTTPException(400, "Give the industry a name")
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"Attach at most {MAX_FILES} documents at a time")

    documents = [
        UploadedDocument(
            filename=f.filename or "untitled",
            content=await f.read(),
            content_type=f.content_type,
        )
        for f in files
    ]
    # Fail here rather than inside the background task, so the browser gets a
    # usable error instead of a job that immediately dies.
    try:
        validate_documents(documents)
    except FilingAnalysisError as e:
        raise HTTPException(e.status_code, str(e)) from e

    analysis = start_industry_analysis(
        title=title.strip(),
        prompt=(prompt or "").strip() or None,
        documents=documents,
        settings=settings,
    )
    log.info(
        "Started industry analysis %s (%r, %d documents)",
        analysis.id,
        analysis.title,
        len(documents),
    )
    return _out(analysis)


@router.get("/{analysis_id}", response_model=IndustryAnalysisOut)
async def read_industry(analysis_id: str) -> IndustryAnalysisOut:
    analysis = get_industry(analysis_id)
    if analysis is None:
        raise HTTPException(
            404, "Industry analysis not found — it may have expired or the API restarted"
        )
    return _out(analysis)


@router.delete("/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_industry_analysis(analysis_id: str) -> None:
    if not delete_industry(analysis_id):
        raise HTTPException(404, "Industry analysis not found")
