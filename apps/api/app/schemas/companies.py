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
