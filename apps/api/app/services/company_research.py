"""Research what a company actually does, from the open web.

The filings tell you the numbers; they rarely tell you how the money is made.
This adds a second, separate Claude call per company with the server-side
`web_search` / `web_fetch` tools enabled, so Claude reads the company's own site
and recent coverage and writes up the revenue model and recent news.

Two things make this risky and are handled in the prompt rather than in code:

  * **Identity.** UK trading names collide constantly, and a company number is
    the only reliable key. The prompt insists on confirming the site belongs to
    this registered company — by number, registered office or filed name — and
    on saying so plainly when it cannot.
  * **Provenance.** Web copy is marketing, not audited fact. Every claim has to
    say where it came from, and web claims must not be mixed into the filed
    figures.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.filing_analysis import AnalysisResult, FilingAnalysisError

log = logging.getLogger("financial-overview.company_research")

# Server-side tools. Dynamic filtering is built into these versions — do not
# also declare code_execution, which creates a second execution environment.
RESEARCH_TOOLS: list[dict[str, Any]] = [
    {
        "type": "web_search_20260209",
        "name": "web_search",
        "max_uses": 8,
        "user_location": {"type": "approximate", "country": "GB"},
    },
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 8},
]

# A long server-tool turn can stop with pause_turn when the server-side loop
# hits its iteration limit; resend once to let it resume.
MAX_CONTINUATIONS = 1

RESEARCH_SYSTEM_PROMPT = """You are a research analyst profiling a UK company. You \
have its filed accounts already summarised, and you can search and read the open web.

Identity comes first. UK trading names collide constantly and the company number is \
the only reliable key. Before describing any business, confirm the website or article \
actually belongs to this registered company — look for the company number, the \
registered office, or the registered name in the site's footer, terms, or contact \
page. If you cannot confirm it, say so and describe only what the filings support. \
Never profile a different company that happens to share a name.

Separate what you know from where you learned it. A figure from the accounts is filed \
and audited or at least filed; a claim from a company's own website is marketing; a \
claim from an article is reporting. Attribute each one. Never merge a web figure into \
the filed figures, and never state a revenue number from a website as if it were filed.

Say plainly when the web gives you nothing. A great many UK companies have no website, \
no coverage, and nothing to find — "no online presence found" is a perfectly good \
answer and far more useful than a paragraph of inference.

Write in plain British English. Be concise and concrete."""

RESEARCH_INSTRUCTIONS = """Research this company and produce Markdown with these \
sections:

## What they do
Two or three sentences: the business in plain terms, the market it serves, and how \
confident you are that this is the right company (say which evidence tied the website \
to the registered company).

## Revenue model
How the money is made. Cover the revenue streams you can evidence — products, \
services, subscriptions, commission, licensing, rent, interest — and how they are \
priced and billed where that is visible. Tie it back to the accounts where you can: \
if turnover, margin, employee numbers or fixed assets support or contradict the \
picture the website paints, say so. Mark each claim as from the filings or from the \
web.

## Recent news
What has happened in roughly the last 18 months: funding, acquisitions, leadership \
changes, contract wins, restructuring, legal or regulatory events, notable coverage. \
Date each item and say where it was reported. If there is nothing, say so — do not \
pad this section.

## Sources
A bullet per source, each a title and its URL. Mark the company's own site as such."""


def build_research_prompt(
    *,
    company_name: str,
    company_number: str,
    trading_name: str | None,
    registered_office: str | None,
    sic_codes: list[str],
    filings_review: str | None,
) -> str:
    lines = [
        f"Registered name: {company_name}",
        f"Company number: {company_number} (UK, Companies House)",
    ]
    if trading_name:
        lines.append(
            f"Trading name: {trading_name} — the business may be known online under "
            "this name rather than its registered name."
        )
    if registered_office:
        lines.append(f"Registered office: {registered_office}")
    if sic_codes:
        lines.append(f"SIC codes: {', '.join(sic_codes)}")
    if filings_review:
        lines.append(
            "\nReview of this company's filed accounts, for grounding:\n\n"
            f"{filings_review}"
        )
    lines.append("\n" + RESEARCH_INSTRUCTIONS)
    return "\n".join(lines)


async def research_company(
    *,
    company_name: str,
    company_number: str,
    trading_name: str | None = None,
    registered_office: str | None = None,
    sic_codes: list[str] | None = None,
    filings_review: str | None = None,
    api_key: str | None,
    model: str,
    max_tokens: int = 4000,
) -> AnalysisResult:
    if not api_key:
        raise FilingAnalysisError("ANTHROPIC_API_KEY is not configured", 503)

    try:
        from anthropic import AsyncAnthropic
    except ImportError as e:  # pragma: no cover - dependency is declared
        raise FilingAnalysisError(f"anthropic SDK not installed: {e}", 500) from e

    client = AsyncAnthropic(api_key=api_key, timeout=600.0, max_retries=2)
    prompt = build_research_prompt(
        company_name=company_name,
        company_number=company_number,
        trading_name=trading_name,
        registered_office=registered_office,
        sic_codes=sic_codes or [],
        filings_review=filings_review,
    )
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

    log.info("Researching %s (%s) on the web", company_name, company_number)
    message = None
    try:
        for attempt in range(MAX_CONTINUATIONS + 1):
            message = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=RESEARCH_SYSTEM_PROMPT,
                messages=messages,
                tools=RESEARCH_TOOLS,
            )
            if message.stop_reason != "pause_turn":
                break
            if attempt < MAX_CONTINUATIONS:
                # Resend the turn as-is; the server resumes from the trailing
                # server_tool_use block. No "continue" message — that confuses it.
                messages = [messages[0], {"role": "assistant", "content": message.content}]
    except Exception as e:
        status = getattr(e, "status_code", None)
        raise FilingAnalysisError(f"Claude web research failed: {e}", status or 502) from e

    if message is None:  # pragma: no cover - loop always runs once
        raise FilingAnalysisError("Claude returned no research response", 502)
    if message.stop_reason == "refusal":
        raise FilingAnalysisError("Claude declined to research this company", 502)

    markdown = "\n".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    ).strip()
    if not markdown:
        raise FilingAnalysisError("Claude returned an empty research response", 502)
    if message.stop_reason == "pause_turn":
        markdown += (
            "\n\n> _Research stopped early after the search budget was used; "
            "the sections above may be incomplete._"
        )

    usage = getattr(message, "usage", None)
    return AnalysisResult(
        markdown=markdown,
        model=message.model,
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
    )
