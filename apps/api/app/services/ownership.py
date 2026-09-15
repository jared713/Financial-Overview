"""Who owns the company, from the Companies House record.

Two sources, because neither is complete on its own:

  * **The PSC register** is structured and reliable but only reaches beneficial
    owners above 25%, and it stops at the first corporate layer — a PSC that is
    itself a holding company tells you little about who is behind it. Listed
    companies are exempt from it altogether.
  * **Confirmation statements** carry the actual shareholder list, with share
    counts, but only in the PDF: in full every third year and as changes in
    between. Capital filings (allotments, statements of capital) fill in the
    share structure.

So the structured PSC data and the filed PDFs both go to Claude, which reconciles
them and is explicit about what the record does not show.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from app.services.companies_house import FilingDocument
from app.services.filing_analysis import AnalysisResult, FilingAnalysisError

log = logging.getLogger("financial-overview.ownership")

MAX_OWNERSHIP_PDF_BYTES = 12 * 1024 * 1024

OWNERSHIP_SYSTEM_PROMPT = """You are reading the Companies House record to establish \
who owns and controls a UK company.

Work only from what is filed. Two sources are given: the PSC (persons with significant \
control) register as structured data, and filed documents — confirmation statements, \
which list shareholders, and capital filings, which show share structure.

Know what each source can and cannot tell you. The PSC register only captures control \
above 25%, so a company can have real investors who never appear on it. It also stops \
at the first layer: if the PSC is a holding company or a nominee, the people behind it \
are not in this record, and you should say so rather than imply the holding company is \
the ultimate owner. Confirmation statements list shareholders in full only every third \
year — an intervening one shows changes, so an old full list plus later changes may be \
the best available picture, and you should date what you give. Companies traded on a \
regulated market are exempt from the PSC regime entirely; their register being empty \
means nothing about their ownership.

Never infer a shareholding that is not filed, never convert a nature-of-control band \
into a precise percentage, and never guess at who sits behind a corporate holder. \
"Not filed" and "the record does not show" are the right answers when that is the case.

Write in plain British English. Be concise."""

OWNERSHIP_INSTRUCTIONS = """Produce Markdown with these sections:

## Shareholders
A table of the shareholders named in the filings: name, shares held, share class, and \
the percentage where the filing gives enough to state it exactly. Give the date of the \
filing each row came from. If no shareholder list has been filed, say so and leave the \
table out.

## Significant control
A bullet per entry on the PSC register: who they are, whether a person or a company, \
the nature of their control as filed (share band, voting band, right to appoint \
directors, significant influence), and when they were notified. Mark any entry that has \
ceased. Where a PSC is itself a company, say plainly that the record stops there and \
name what it does give (company number, jurisdiction) so the chain can be followed by \
hand. If the register is empty, say why if a statement explains it.

## Share structure
Total shares in issue by class, nominal value, and any change visible across the capital \
filings — allotments, buybacks, new classes.

## What the record does not show
The limits that matter for this company: a shareholder list older than the latest \
confirmation statement, ownership held through a nominee or holding company, holdings \
below the PSC threshold, or a PSC exemption. Be specific to this company rather than \
generic."""


def summarise_psc(psc: dict[str, Any], statements: dict[str, Any]) -> str:
    """Flatten the PSC register into text for the prompt.

    Passed as a readable summary rather than raw JSON so the model reads the
    fields that matter and is not distracted by links and self-references.
    """
    lines: list[str] = []
    items = psc.get("items") or []
    if not items:
        lines.append("PSC register: no active entries returned.")
    for item in items:
        name = item.get("name") or "unnamed"
        kind = (item.get("kind") or "").replace("-", " ")
        natures = ", ".join(
            str(n).replace("-", " ") for n in (item.get("natures_of_control") or [])
        )
        parts = [f"- {name} ({kind})"]
        if natures:
            parts.append(f"  control: {natures}")
        if item.get("notified_on"):
            parts.append(f"  notified on: {item['notified_on']}")
        if item.get("ceased_on"):
            parts.append(f"  CEASED on: {item['ceased_on']}")
        identification = item.get("identification") or {}
        ident = ", ".join(
            f"{key.replace('_', ' ')}: {value}"
            for key, value in identification.items()
            if value
        )
        if ident:
            parts.append(f"  identification: {ident}")
        if item.get("nationality"):
            parts.append(f"  nationality: {item['nationality']}")
        if item.get("country_of_residence"):
            parts.append(f"  country of residence: {item['country_of_residence']}")
        lines.append("\n".join(parts))

    for statement in statements.get("items") or []:
        text = str(statement.get("statement") or "").replace("-", " ")
        if text:
            lines.append(f"- Register statement: {text} (as of {statement.get('notified_on')})")

    return "\n".join(lines) or "PSC register: nothing returned."


def build_ownership_content(
    *,
    company_name: str,
    company_number: str,
    psc_summary: str,
    documents: list[FilingDocument],
) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"Company: {company_name} (Companies House number {company_number}).\n\n"
                f"PSC register as filed:\n{psc_summary}"
            ),
        }
    ]
    for doc in documents:
        filing = doc.filing
        label = (
            f"Filed document — {(filing.description or filing.type or 'filing')}"
            f", dated {filing.date or 'unknown'}"
        )
        content.append({"type": "text", "text": label})
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
    if not documents:
        content.append(
            {
                "type": "text",
                "text": (
                    "No confirmation statement or capital filing was available to "
                    "download for this company."
                ),
            }
        )
    content.append({"type": "text", "text": OWNERSHIP_INSTRUCTIONS})
    return content


async def analyse_ownership(
    *,
    company_name: str,
    company_number: str,
    psc: dict[str, Any],
    statements: dict[str, Any],
    documents: list[FilingDocument],
    api_key: str | None,
    model: str,
    max_tokens: int = 4000,
) -> AnalysisResult:
    if not api_key:
        raise FilingAnalysisError("ANTHROPIC_API_KEY is not configured", 503)

    # Confirmation statements are small, but guard anyway.
    kept: list[FilingDocument] = []
    total = 0
    for doc in documents:
        if total + len(doc.content) > MAX_OWNERSHIP_PDF_BYTES:
            log.info("Skipping %s: ownership PDF budget reached", doc.filing.transaction_id)
            continue
        kept.append(doc)
        total += len(doc.content)

    try:
        from anthropic import AsyncAnthropic
    except ImportError as e:  # pragma: no cover - dependency is declared
        raise FilingAnalysisError(f"anthropic SDK not installed: {e}", 500) from e

    client = AsyncAnthropic(api_key=api_key, timeout=600.0, max_retries=2)
    content = build_ownership_content(
        company_name=company_name,
        company_number=company_number,
        psc_summary=summarise_psc(psc, statements),
        documents=kept,
    )

    log.info(
        "Reading ownership for %s (%s): %d PSC entries, %d document(s)",
        company_name,
        company_number,
        len(psc.get("items") or []),
        len(kept),
    )
    try:
        message = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=OWNERSHIP_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
    except Exception as e:
        status = getattr(e, "status_code", None)
        raise FilingAnalysisError(f"Claude ownership review failed: {e}", status or 502) from e

    if message.stop_reason == "refusal":
        raise FilingAnalysisError("Claude declined to review this company's ownership", 502)

    markdown = "\n".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    ).strip()
    if not markdown:
        raise FilingAnalysisError("Claude returned an empty ownership review", 502)

    usage = getattr(message, "usage", None)
    return AnalysisResult(
        markdown=markdown,
        model=message.model,
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
    )
