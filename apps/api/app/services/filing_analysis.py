"""Send Companies House account PDFs to Claude for review.

The Messages API takes PDFs directly as `document` content blocks, so the
filings go up as-is — no OCR or text extraction step, which matters because
plenty of small-company accounts on Companies House are scanned images.

All selected filings go up in a single message so the model can compare them
against each other rather than summarising each in isolation.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Any

from app.services.companies_house import FilingDocument

log = logging.getLogger("financial-overview.filing_analysis")

# Anthropic caps a request at 32MB; base64 inflates by ~33%, so cap the raw
# total below that with room for the prompt itself.
MAX_TOTAL_PDF_BYTES = 20 * 1024 * 1024
MAX_FILINGS_PER_ANALYSIS = 6

SYSTEM_PROMPT = """You are a financial analyst reviewing statutory accounts filed \
at Companies House (UK). You are given the filed PDFs themselves, which may be \
full audited accounts, abridged or filleted small-company accounts, or micro-entity \
accounts under FRS 105.

Ground every figure you state in the filings provided. Quote the figure as filed, \
with its period, and name which filing it came from. If a figure is not disclosed — \
which is common and expected in filleted or micro-entity accounts, where there is \
often no profit and loss account — say "not disclosed" rather than estimating or \
inferring it. Never invent a number.

Write in plain British English for a reader who understands accounts but has not \
read these ones. Be concise and specific; skip boilerplate."""

SUMMARY_INSTRUCTIONS = """Review the filing above and produce Markdown with these sections:

## Filing
Company, period covered, accounts type (full / small / abridged / filleted / \
micro-entity / dormant), whether audited, and the filing date.

## Key figures
A Markdown table of the figures actually disclosed — typically turnover, operating \
profit, profit before tax, fixed assets, current assets, creditors due within one \
year, creditors due after one year, net current assets, net assets / shareholders' \
funds, cash at bank, and average employees. Show the comparative (prior year) column \
where the filing includes it. Mark anything absent as "not disclosed".

## What stands out
Three to six bullets: the notable movements, balance-sheet strengths or strains, \
and anything in the notes worth a second look (related party transactions, going \
concern wording, post balance sheet events, changes in accounting policy).

## Watch-outs
Anything that limits what can be read from this filing — filleted accounts, a short \
or long accounting period, a change of year end, restated comparatives, or an audit \
qualification."""

COMPARISON_INSTRUCTIONS = """Review all {count} filings above and produce Markdown \
with these sections:

## Overview
Two or three sentences on the company and the period span the filings cover.

## Trend table
One Markdown table with a row per key figure and a column per accounting period \
(oldest period on the left, newest on the right). Cover the figures disclosed across \
the filings — typically turnover, operating profit, profit before tax, fixed assets, \
current assets, cash at bank, creditors due within one year, creditors due after one \
year, net current assets, net assets / shareholders' funds, and average employees. \
Use "not disclosed" where a filing does not give the figure.

## Trajectory
Four to eight bullets on how the business has moved across these periods: growth or \
contraction, margin direction, balance-sheet strength, debt, cash, headcount. Give \
percentages or absolute movements, and name the periods being compared.

## Comparability
Flag anything that makes the periods less than like-for-like: a change of accounting \
basis or year end, restated comparatives, a short period, a move between full and \
filleted accounts, or a change of auditor.

## Watch-outs
The three to five things you would want answered before relying on these accounts."""


@dataclass
class AnalysisResult:
    markdown: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class FilingAnalysisError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def _filing_label(doc: FilingDocument) -> str:
    filing = doc.filing
    period = filing.made_up_to or "period not stated"
    parts = [f"Filing {filing.transaction_id}: accounts made up to {period}"]
    if filing.date:
        parts.append(f"filed {filing.date}")
    if filing.description:
        parts.append(filing.description.replace("-", " "))
    if filing.paper_filed:
        parts.append("paper filed (scanned image)")
    return " — ".join(parts)


def build_message_content(
    documents: list[FilingDocument],
    company_name: str,
    company_number: str,
    question: str | None = None,
) -> list[dict[str, Any]]:
    """Interleave a label before each PDF so the model can name its sources."""
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"Company: {company_name} (Companies House number {company_number}).\n"
                f"{len(documents)} account filing(s) follow, newest first."
            ),
        }
    ]
    for doc in documents:
        content.append({"type": "text", "text": _filing_label(doc)})
        content.append(
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": base64.standard_b64encode(doc.content).decode("ascii"),
                },
            }
        )

    if len(documents) == 1:
        instructions = SUMMARY_INSTRUCTIONS
    else:
        instructions = COMPARISON_INSTRUCTIONS.format(count=len(documents))
    if question:
        instructions += (
            "\n\n## Answering the specific question\n"
            "Finally, answer this question from the filings, or say plainly that the "
            f"filings do not contain the answer:\n{question.strip()}"
        )
    content.append({"type": "text", "text": instructions})
    return content


async def analyse_filings(
    documents: list[FilingDocument],
    *,
    company_name: str,
    company_number: str,
    api_key: str | None,
    model: str,
    max_tokens: int = 8000,
    question: str | None = None,
) -> AnalysisResult:
    if not api_key:
        raise FilingAnalysisError(
            "ANTHROPIC_API_KEY is not configured on the API service — filings can "
            "still be downloaded, but Claude review is unavailable",
            503,
        )
    if not documents:
        raise FilingAnalysisError("Select at least one filing to analyse", 400)
    if len(documents) > MAX_FILINGS_PER_ANALYSIS:
        raise FilingAnalysisError(
            f"Select at most {MAX_FILINGS_PER_ANALYSIS} filings per analysis", 400
        )
    total = sum(len(d.content) for d in documents)
    if total > MAX_TOTAL_PDF_BYTES:
        raise FilingAnalysisError(
            f"Selected filings total {total // (1024 * 1024)}MB, over the "
            f"{MAX_TOTAL_PDF_BYTES // (1024 * 1024)}MB limit — analyse fewer at a time",
            413,
        )

    try:
        from anthropic import AsyncAnthropic
    except ImportError as e:  # pragma: no cover - dependency is declared
        raise FilingAnalysisError(f"anthropic SDK not installed: {e}", 500) from e

    client = AsyncAnthropic(api_key=api_key, timeout=600.0, max_retries=2)
    content = build_message_content(documents, company_name, company_number, question)

    log.info(
        "Analysing %d filing(s) for %s (%s), %d bytes of PDF",
        len(documents),
        company_name,
        company_number,
        total,
    )
    try:
        message = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
    except Exception as e:
        status = getattr(e, "status_code", None)
        raise FilingAnalysisError(f"Claude request failed: {e}", status or 502) from e

    markdown = "\n".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    ).strip()
    if not markdown:
        raise FilingAnalysisError("Claude returned an empty response", 502)

    usage = getattr(message, "usage", None)
    return AnalysisResult(
        markdown=markdown,
        model=message.model,
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
    )


CROSS_COMPANY_SYSTEM_PROMPT = """You are a financial analyst comparing several UK \
companies from their filed statutory accounts. You are given a written review of \
each company, prepared from its own filings at Companies House.

Work only from the reviews given. Where a review says a figure is "not disclosed", \
keep it as not disclosed — most small UK companies file filleted or micro-entity \
accounts with no profit and loss account, so gaps are normal and must not be filled \
in by inference. Never invent a number, and never carry a figure from one company \
onto another.

Be careful about like-for-like: companies file to different period ends, under \
different accounts regimes, and in different industries. Say so when it limits the \
comparison.

Write in plain British English. Be concise and specific."""

CROSS_COMPANY_INSTRUCTIONS = """Compare the {count} companies reviewed above and produce \
Markdown with these sections:

## Side by side
One Markdown table: a row per key figure, a column per company, using each company's \
most recent period. Put the period end date under each company name in the header so \
the reader can see what is being compared. Cover the figures the reviews actually \
disclose — typically turnover, operating profit, profit before tax, net assets, cash \
at bank, creditors due within one year, creditors due after one year, and average \
employees. Use "not disclosed" where a company does not give the figure.

## How they compare
Five to eight bullets on the differences that matter: relative size, growth, \
profitability, balance-sheet strength, cash, leverage, and headcount efficiency. \
Name the companies and give the figures you are comparing. Where only some companies \
disclose a measure, say which.

## Standouts
The strongest and the weakest on the evidence available, and what specifically makes \
each so. If the filings do not support a judgement, say that instead.

## Comparability caveats
What makes this less than like-for-like — different period ends, different accounts \
regimes (full vs filleted vs micro-entity), different industries, a short period, or \
a company whose figures are largely undisclosed.

## Watch-outs
The three to five things you would want answered before relying on this comparison."""

CROSS_COMPANY_BUSINESS_SECTION = """

Insert this section immediately after "How they compare":

## How they make money
Compare the revenue models described in the reviews: what each company sells, to whom, \
and how that shows up (or fails to show up) in the filed figures. Say which models look \
more durable and why. Where a review could not confirm a company's online presence, say \
so rather than guessing at its model."""


@dataclass
class CompanySummary:
    """One company's own review, as input to the cross-company comparison."""

    company_number: str
    company_name: str
    markdown: str


def build_comparison_content(
    summaries: list[CompanySummary],
    question: str | None = None,
    with_research: bool = False,
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"{len(summaries)} company reviews follow, each prepared from that "
                "company's own filed accounts."
            ),
        }
    ]
    for summary in summaries:
        blocks.append(
            {
                "type": "text",
                "text": (
                    f"--- Review of {summary.company_name} "
                    f"(company number {summary.company_number}) ---\n\n"
                    f"{summary.markdown}"
                ),
            }
        )
    instructions = CROSS_COMPANY_INSTRUCTIONS.format(count=len(summaries))
    if with_research:
        instructions += CROSS_COMPANY_BUSINESS_SECTION
    if question:
        instructions += (
            "\n\n## Answering the specific question\n"
            "Finally, answer this question from the reviews, or say plainly that they "
            f"do not contain the answer:\n{question.strip()}"
        )
    blocks.append({"type": "text", "text": instructions})
    return blocks


async def compare_companies(
    summaries: list[CompanySummary],
    *,
    api_key: str | None,
    model: str,
    max_tokens: int = 8000,
    question: str | None = None,
    with_research: bool = False,
) -> AnalysisResult:
    """Second pass: one comparison across the per-company reviews."""
    if not api_key:
        raise FilingAnalysisError("ANTHROPIC_API_KEY is not configured", 503)
    if len(summaries) < 2:
        raise FilingAnalysisError("Comparison needs at least two companies", 400)

    try:
        from anthropic import AsyncAnthropic
    except ImportError as e:  # pragma: no cover - dependency is declared
        raise FilingAnalysisError(f"anthropic SDK not installed: {e}", 500) from e

    client = AsyncAnthropic(api_key=api_key, timeout=600.0, max_retries=2)
    log.info("Comparing %d companies", len(summaries))
    try:
        message = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=CROSS_COMPANY_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": build_comparison_content(summaries, question, with_research),
                }
            ],
        )
    except Exception as e:
        status = getattr(e, "status_code", None)
        raise FilingAnalysisError(f"Claude comparison failed: {e}", status or 502) from e

    markdown = "\n".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    ).strip()
    if not markdown:
        raise FilingAnalysisError("Claude returned an empty comparison", 502)

    usage = getattr(message, "usage", None)
    return AnalysisResult(
        markdown=markdown,
        model=message.model,
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
    )


REFINE_SYSTEM_PROMPT = SYSTEM_PROMPT + """

You are revising a review you produced earlier. The filed accounts, the previous review \
and what the reader wants changed are all given.

Produce the full revised review, not a description of what you changed and not a diff. \
Carry forward everything that still holds — a request for more on one thing is not a \
request to drop the rest — and keep the sections that came from sources not re-supplied \
here (the web write-up, the ownership record) intact unless the request bears on them. \
Re-read the filings rather than working from your previous wording alone. Where the \
request asks for something the filings do not disclose, say so in the revision rather \
than estimating it."""


def build_refinement_content(
    documents: list[FilingDocument],
    *,
    company_name: str,
    company_number: str,
    previous: str,
    instruction: str,
) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"Company: {company_name} (Companies House number {company_number}).\n"
                f"{len(documents)} filing(s) follow, then the previous review, then what "
                "is being asked for."
            ),
        }
    ]
    for doc in documents:
        content.append({"type": "text", "text": _filing_label(doc)})
        content.append(
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": base64.standard_b64encode(doc.content).decode("ascii"),
                },
            }
        )
    content.append({"type": "text", "text": f"--- Previous review ---\n\n{previous}"})
    content.append(
        {"type": "text", "text": f"What the reader wants changed:\n\n{instruction.strip()}"}
    )
    return content


async def refine_filings_review(
    documents: list[FilingDocument],
    *,
    company_name: str,
    company_number: str,
    previous: str,
    instruction: str,
    api_key: str | None,
    model: str,
    max_tokens: int = 8000,
) -> AnalysisResult:
    if not api_key:
        raise FilingAnalysisError("ANTHROPIC_API_KEY is not configured", 503)
    if not instruction.strip():
        raise FilingAnalysisError("Say what you want changed", 400)

    try:
        from anthropic import AsyncAnthropic
    except ImportError as e:  # pragma: no cover - dependency is declared
        raise FilingAnalysisError(f"anthropic SDK not installed: {e}", 500) from e

    client = AsyncAnthropic(api_key=api_key, timeout=600.0, max_retries=2)
    content = build_refinement_content(
        documents,
        company_name=company_name,
        company_number=company_number,
        previous=previous,
        instruction=instruction,
    )
    log.info("Refining review of %s (%s)", company_name, company_number)
    try:
        message = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=REFINE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
    except Exception as e:
        status = getattr(e, "status_code", None)
        raise FilingAnalysisError(f"Claude revision failed: {e}", status or 502) from e

    if message.stop_reason == "refusal":
        raise FilingAnalysisError("Claude declined to revise this review", 502)

    markdown = "\n".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    ).strip()
    if not markdown:
        raise FilingAnalysisError("Claude returned an empty revision", 502)

    usage = getattr(message, "usage", None)
    return AnalysisResult(
        markdown=markdown,
        model=message.model,
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
    )
