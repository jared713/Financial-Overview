from pydantic import BaseModel, Field


class FeatureStatus(BaseModel):
    companies_house: bool
    claude_review: bool
    model: str | None = None
    # False when results are saved to ephemeral disk (no volume mounted).
    saving_is_durable: bool = True


class CompanySearchHit(BaseModel):
    company_number: str
    title: str
    company_status: str | None = None
    company_type: str | None = None
    date_of_creation: str | None = None
    address_snippet: str | None = None


class CompanyProfile(BaseModel):
    company_number: str
    company_name: str
    company_status: str | None = None
    company_type: str | None = None
    date_of_creation: str | None = None
    registered_office: str | None = None
    sic_codes: list[str] = []
    accounts_last_made_up_to: str | None = None
    accounts_next_due: str | None = None


class FilingOut(BaseModel):
    transaction_id: str
    date: str | None = None
    type: str | None = None
    description: str | None = None
    made_up_to: str | None = None
    paper_filed: bool = False
    pages: int | None = None
    downloadable: bool = True


class AnalyseRequest(BaseModel):
    transaction_ids: list[str] = Field(min_length=1, max_length=6)
    question: str | None = None


class AnalysedFiling(BaseModel):
    transaction_id: str
    made_up_to: str | None = None
    date: str | None = None
    description: str | None = None
    size_bytes: int


class AnalysisOut(BaseModel):
    company_number: str
    company_name: str
    filings: list[AnalysedFiling]
    markdown: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class AnalyseCompanyRequest(BaseModel):
    company_number: str
    transaction_ids: list[str] = Field(min_length=1, max_length=4)
    # Set when the business is known online by something other than its
    # registered name, which is the common case.
    trading_name: str | None = Field(default=None, max_length=200)
    # Web research (revenue model, recent news) is part of every review; the
    # flag stays so the API can skip it, but nothing in the UI turns it off.
    research: bool = True


class RefineRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=4000)


class CompanyAnalysisOut(BaseModel):
    id: str
    parent_id: str | None = None
    root_id: str = ""
    instruction: str | None = None
    created_at: float = 0.0
    status: str
    company_number: str
    company_name: str
    research: bool = False
    filings: list[AnalysedFiling] = []
    markdown: str | None = None
    error: str | None = None
    research_markdown: str | None = None
    research_error: str | None = None
    ownership_markdown: str | None = None
    ownership_error: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0


class CompareRequest(BaseModel):
    analysis_ids: list[str] = Field(min_length=2, max_length=5)
    # Optional steer for the comparison, e.g. "focus on cash generation".
    guidance: str | None = None


class ComparedCompany(BaseModel):
    company_number: str
    company_name: str


class ComparisonOut(BaseModel):
    id: str
    status: str
    analysis_ids: list[str]
    companies: list[ComparedCompany] = []
    markdown: str | None = None
    error: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0


class SavedItem(BaseModel):
    kind: str  # analysis | comparison
    id: str
    created_at: float
    title: str
    subtitle: str = ""
    status: str
    research: bool = False
    revisions: int = 1


class IndustryDocumentOut(BaseModel):
    filename: str
    size_bytes: int = 0


class IndustryAnalysisOut(BaseModel):
    id: str
    parent_id: str | None = None
    root_id: str = ""
    instruction: str | None = None
    created_at: float = 0.0
    status: str
    title: str
    prompt: str | None = None
    documents: list[IndustryDocumentOut] = []
    markdown: str | None = None
    error: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
