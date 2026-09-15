from pydantic import BaseModel, Field


class FeatureStatus(BaseModel):
    companies_house: bool
    claude_review: bool
    model: str | None = None


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


class CompanySelection(BaseModel):
    company_number: str
    transaction_ids: list[str] = Field(min_length=1, max_length=4)


class AnalysisRequest(BaseModel):
    companies: list[CompanySelection] = Field(min_length=1, max_length=5)
    question: str | None = None


class CompanyRunOut(BaseModel):
    company_number: str
    company_name: str
    status: str
    filings: list[AnalysedFiling] = []
    markdown: str | None = None
    error: str | None = None


class AnalysisJobOut(BaseModel):
    id: str
    status: str
    companies: list[CompanyRunOut]
    finished: int
    total: int
    comparison_markdown: str | None = None
    comparison_error: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
