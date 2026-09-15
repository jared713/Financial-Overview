"""The two things this app produces: a company analysis and a comparison.

Kept apart from the job runner and the store so both can share them without an
import cycle.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from app.services.filing_analysis import CompanySummary


@dataclass
class AnalysedFilingRef:
    transaction_id: str
    made_up_to: str | None = None
    date: str | None = None
    description: str | None = None
    size_bytes: int = 0


@dataclass
class CompanyAnalysis:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    company_number: str = ""
    company_name: str = ""
    status: str = "running"  # running | done | error
    created_at: float = field(default_factory=time.time)
    research: bool = False
    filings: list[AnalysedFilingRef] = field(default_factory=list)
    markdown: str | None = None
    error: str | None = None
    research_markdown: str | None = None
    research_error: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0

    def as_summary(self) -> CompanySummary:
        """What the comparison reads: the accounts review plus any web research."""
        markdown = self.markdown or ""
        if self.research_markdown:
            markdown = f"{markdown}\n\n### Business and recent news\n\n{self.research_markdown}"
        return CompanySummary(
            company_number=self.company_number,
            company_name=self.company_name or self.company_number,
            markdown=markdown,
        )


@dataclass
class Comparison:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    analysis_ids: list[str] = field(default_factory=list)
    status: str = "running"  # running | done | error
    created_at: float = field(default_factory=time.time)
    guidance: str | None = None
    companies: list[tuple[str, str]] = field(default_factory=list)  # (number, name)
    markdown: str | None = None
    error: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
