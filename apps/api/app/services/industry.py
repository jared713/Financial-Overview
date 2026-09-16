"""Analyse an industry from documents the user supplies.

Nothing here comes from Companies House. You upload what you have — a
government market review, a regulator's report, a trade body's survey — say
what you want out of it, and Claude reads them together.

PDFs go up as `document` blocks, as filings do. Plain-text formats go up as
text, because wrapping them in a PDF would only lose fidelity.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Any

from app.services.filing_analysis import AnalysisResult, FilingAnalysisError

log = logging.getLogger("financial-overview.industry")

MAX_FILES = 8
# Anthropic caps a request at 32MB and base64 inflates by a third, so keep the
# raw total well under it.
MAX_TOTAL_BYTES = 20 * 1024 * 1024

PDF_TYPE = "application/pdf"
TEXT_SUFFIXES = (".txt", ".md", ".markdown", ".csv", ".tsv", ".json")

DEFAULT_PROMPT = (
    "Summarise these documents for someone assessing this industry: what the market "
    "is, how big it is, what is driving it, and what the risks are."
)

INDUSTRY_SYSTEM_PROMPT = """You are an analyst reading documents someone has given you \
about an industry or market, to answer what they have asked of them.

Work from the documents. Every figure, claim and forecast you give should be traceable \
to one of them — name which document it came from, and the section, table or page where \
that helps the reader find it. Where documents disagree, say so and give both.

Distinguish what a document states from what you are inferring. An inference drawn \
across two documents can be valuable, but it must be labelled as yours rather than \
presented as sourced. You may use what you know about the sector to frame and interpret \
the material, but keep it clearly separate from what the documents say, and never \
introduce outside figures as if they came from the documents.

Be direct about limits. Say what the documents do not cover, where they are out of date, \
and where a source's own position would colour what it reports — a trade body's market \
sizing, a vendor's white paper, a department's account of its own policy. If the request \
asks something the documents cannot answer, say that plainly rather than filling the gap.

Write in plain British English. Be concise and concrete; prefer specific figures with \
their source over general statements."""

STRUCTURE_FALLBACK = """

The request above does not specify a structure, so use these sections: **Summary** \
(what these documents amount to, in a short paragraph), **Key figures** (a table of the \
numbers that matter, each with its source), **What is driving it**, **Risks and \
headwinds**, **What the documents do not cover**, and **Sources** (a bullet per \
document, with what it is and who produced it)."""


@dataclass
class UploadedDocument:
    filename: str
    content: bytes
    content_type: str | None = None

    @property
    def is_pdf(self) -> bool:
        return (self.content_type or "").lower() == PDF_TYPE or self.filename.lower().endswith(
            ".pdf"
        )

    @property
    def is_text(self) -> bool:
        lowered = self.filename.lower()
        return lowered.endswith(TEXT_SUFFIXES) or (self.content_type or "").startswith(
            "text/"
        )


def validate_documents(documents: list[UploadedDocument]) -> None:
    if not documents:
        raise FilingAnalysisError("Attach at least one document to analyse", 400)
    if len(documents) > MAX_FILES:
        raise FilingAnalysisError(f"Attach at most {MAX_FILES} documents at a time", 400)

    unsupported = [d.filename for d in documents if not (d.is_pdf or d.is_text)]
    if unsupported:
        raise FilingAnalysisError(
            "Only PDF and plain-text files can be read: "
            f"{', '.join(unsupported)}. Export other formats to PDF first.",
            400,
        )

    total = sum(len(d.content) for d in documents)
    if total > MAX_TOTAL_BYTES:
        raise FilingAnalysisError(
            f"The documents total {total // (1024 * 1024)}MB, over the "
            f"{MAX_TOTAL_BYTES // (1024 * 1024)}MB limit — upload fewer at a time",
            413,
        )
    empty = [d.filename for d in documents if not d.content]
    if empty:
        raise FilingAnalysisError(f"These files are empty: {', '.join(empty)}", 400)


def build_industry_content(
    *, title: str, prompt: str | None, documents: list[UploadedDocument]
) -> list[dict[str, Any]]:
    request = (prompt or "").strip() or DEFAULT_PROMPT
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"Industry: {title}\n\n"
                f"{len(documents)} document(s) follow, then what is being asked of them."
            ),
        }
    ]
    for doc in documents:
        content.append({"type": "text", "text": f"--- Document: {doc.filename} ---"})
        if doc.is_pdf:
            content.append(
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": PDF_TYPE,
                        "data": base64.standard_b64encode(doc.content).decode("ascii"),
                    },
                }
            )
        else:
            text = doc.content.decode("utf-8", errors="replace")
            content.append({"type": "text", "text": text})

    instruction = f"What is being asked of these documents:\n\n{request}"
    if not prompt or not prompt.strip():
        instruction += STRUCTURE_FALLBACK
    content.append({"type": "text", "text": instruction})
    return content


async def analyse_industry(
    *,
    title: str,
    prompt: str | None,
    documents: list[UploadedDocument],
    api_key: str | None,
    model: str,
    max_tokens: int = 8000,
) -> AnalysisResult:
    if not api_key:
        raise FilingAnalysisError("ANTHROPIC_API_KEY is not configured", 503)
    validate_documents(documents)

    try:
        from anthropic import AsyncAnthropic
    except ImportError as e:  # pragma: no cover - dependency is declared
        raise FilingAnalysisError(f"anthropic SDK not installed: {e}", 500) from e

    client = AsyncAnthropic(api_key=api_key, timeout=600.0, max_retries=2)
    content = build_industry_content(title=title, prompt=prompt, documents=documents)

    log.info(
        "Analysing industry %r from %d document(s), %d bytes",
        title,
        len(documents),
        sum(len(d.content) for d in documents),
    )
    try:
        message = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=INDUSTRY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
    except Exception as e:
        status = getattr(e, "status_code", None)
        raise FilingAnalysisError(f"Claude industry review failed: {e}", status or 502) from e

    if message.stop_reason == "refusal":
        raise FilingAnalysisError("Claude declined to analyse these documents", 502)

    markdown = "\n".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    ).strip()
    if not markdown:
        raise FilingAnalysisError("Claude returned an empty industry review", 502)

    usage = getattr(message, "usage", None)
    return AnalysisResult(
        markdown=markdown,
        model=message.model,
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
    )
