import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.routers import analyses as analyses_router
from app.services import analysis_jobs
from app.services.analysis_jobs import (
    CompanyAnalysis,
    _registered_office,
    _select_filings,
    start_analysis,
    start_comparison,
)
from app.services.companies_house import CompaniesHouseError, Filing, FilingDocument
from app.services.filing_analysis import (
    AnalysisResult,
    CompanySummary,
    FilingAnalysisError,
    build_comparison_content,
)

SETTINGS = Settings(
    companies_house_api_key="ch-key",
    anthropic_api_key="sk-test",
    anthropic_model="claude-test",
)


def _filing(txn: str, date: str, made_up_to: str) -> Filing:
    return Filing(
        transaction_id=txn,
        date=date,
        type="AA",
        description="accounts-with-accounts-type-full",
        made_up_to=made_up_to,
        document_id=f"doc-{txn}",
    )


FILINGS = [
    _filing("t-2024", "2024-05-16", "2024-02-24"),
    _filing("t-2023", "2023-05-12", "2023-02-25"),
    _filing("t-2022", "2022-05-20", "2022-02-26"),
]


def test_select_filings_orders_oldest_first():
    assert [f.transaction_id for f in _select_filings(FILINGS, ["t-2024", "t-2022"])] == [
        "t-2022",
        "t-2024",
    ]


def test_select_filings_rejects_unknown_transaction():
    with pytest.raises(CompaniesHouseError) as excinfo:
        _select_filings(FILINGS, ["nope"])
    assert "nope" in str(excinfo.value)


def test_registered_office_joins_the_parts_that_exist():
    assert (
        _registered_office(
            {
                "registered_office_address": {
                    "address_line_1": "Tesco House",
                    "locality": "Welwyn Garden City",
                    "postal_code": "AL7 1GA",
                }
            }
        )
        == "Tesco House, Welwyn Garden City, AL7 1GA"
    )
    assert _registered_office({}) is None


def test_analysis_summary_folds_in_research():
    analysis = CompanyAnalysis(
        id="a1",
        company_number="00445790",
        company_name="TESCO PLC",
        markdown="## Filing\nAccounts review.",
        research_markdown="## Revenue model\nThey sell groceries.",
    )
    summary = analysis.as_summary()
    assert "Accounts review." in summary.markdown
    assert "They sell groceries." in summary.markdown
    assert summary.company_name == "TESCO PLC"


def test_analysis_summary_without_research_is_just_the_review():
    analysis = CompanyAnalysis(
        id="a1", company_number="00445790", company_name="TESCO PLC", markdown="review"
    )
    assert analysis.as_summary().markdown == "review"


def test_build_comparison_content_carries_each_review():
    blocks = build_comparison_content(
        [
            CompanySummary("00445790", "TESCO PLC", "Tesco review"),
            CompanySummary("00989096", "J SAINSBURY PLC", "Sainsbury review"),
        ],
        question="Which is growing faster?",
    )
    assert [b["type"] for b in blocks] == ["text", "text", "text", "text"]
    assert "Tesco review" in blocks[1]["text"]
    assert "Side by side" in blocks[-1]["text"]
    assert "Which is growing faster?" in blocks[-1]["text"]


class FakeClient:
    def __init__(self, api_key, **kwargs):
        pass

    async def list_account_filings(self, company_number, *, limit=50):
        if company_number == "99999999":
            raise CompaniesHouseError("Not found at Companies House", 404)
        return FILINGS

    async def get_company(self, company_number):
        return {
            "company_name": f"COMPANY {company_number}",
            "sic_codes": ["47110"],
            "registered_office_address": {"address_line_1": "1 High Street"},
        }

    async def fetch_filing_documents(self, filings):
        return [FilingDocument(filing=f, content=b"%PDF-1.4 fake") for f in filings]


@pytest.fixture
def fake_backends(monkeypatch):
    calls: dict[str, list] = {"analyse": [], "research": [], "compare": []}

    async def fake_analyse(documents, **kwargs):
        calls["analyse"].append(kwargs["company_number"])
        return AnalysisResult(
            markdown=f"review of {kwargs['company_name']}",
            model="claude-test",
            input_tokens=100,
            output_tokens=10,
        )

    async def fake_research(**kwargs):
        calls["research"].append((kwargs["company_number"], kwargs["trading_name"]))
        return AnalysisResult(
            markdown="## Revenue model\nWidgets.",
            model="claude-test",
            input_tokens=20,
            output_tokens=5,
        )

    async def fake_compare(summaries, **kwargs):
        calls["compare"].append(
            {
                "summaries": [s.markdown for s in summaries],
                "question": kwargs.get("question"),
                "with_research": kwargs.get("with_research"),
            }
        )
        return AnalysisResult(
            markdown="the comparison", model="claude-test", input_tokens=50, output_tokens=5
        )

    monkeypatch.setattr(analysis_jobs, "CompaniesHouseClient", FakeClient)
    monkeypatch.setattr(analysis_jobs, "analyse_filings", fake_analyse)
    monkeypatch.setattr(analysis_jobs, "research_company", fake_research)
    monkeypatch.setattr(analysis_jobs, "compare_companies", fake_compare)
    return calls


async def _settle() -> None:
    """Let the fire-and-forget task created by start_* run to completion."""
    for _ in range(10):
        await __import__("asyncio").sleep(0)


async def test_company_analysis_runs_and_records_filings(fake_backends):
    analysis = start_analysis(
        company_number="00445790",
        transaction_ids=["t-2024", "t-2023"],
        trading_name=None,
        research=False,
        settings=SETTINGS,
    )
    await _settle()

    assert analysis.status == "done"
    assert analysis.company_name == "COMPANY 00445790"
    assert analysis.markdown == "review of COMPANY 00445790"
    assert [f.transaction_id for f in analysis.filings] == ["t-2023", "t-2024"]
    assert analysis.input_tokens == 100
    assert fake_backends["research"] == []


async def test_research_runs_when_asked_and_uses_the_trading_name(fake_backends):
    analysis = start_analysis(
        company_number="00445790",
        transaction_ids=["t-2024"],
        trading_name="Tesco",
        research=True,
        settings=SETTINGS,
    )
    await _settle()

    assert fake_backends["research"] == [("00445790", "Tesco")]
    assert analysis.research_markdown == "## Revenue model\nWidgets."
    assert analysis.input_tokens == 120


async def test_research_failure_leaves_the_accounts_review_intact(monkeypatch, fake_backends):
    async def broken(**kwargs):
        raise FilingAnalysisError("boom")

    monkeypatch.setattr(analysis_jobs, "research_company", broken)
    analysis = start_analysis(
        company_number="00445790",
        transaction_ids=["t-2024"],
        trading_name=None,
        research=True,
        settings=SETTINGS,
    )
    await _settle()

    assert analysis.status == "done"
    assert analysis.markdown is not None
    assert "boom" in (analysis.research_error or "")


async def test_failed_company_records_the_error(fake_backends):
    analysis = start_analysis(
        company_number="99999999",
        transaction_ids=["t-2024"],
        trading_name=None,
        research=False,
        settings=SETTINGS,
    )
    await _settle()

    assert analysis.status == "error"
    assert "Not found" in (analysis.error or "")


async def test_comparison_reads_the_finished_analyses(fake_backends):
    first = start_analysis(
        company_number="00445790",
        transaction_ids=["t-2024"],
        trading_name=None,
        research=True,
        settings=SETTINGS,
    )
    second = start_analysis(
        company_number="00989096",
        transaction_ids=["t-2024"],
        trading_name=None,
        research=False,
        settings=SETTINGS,
    )
    await _settle()

    comparison = start_comparison(
        analyses=[first, second], guidance="Focus on cash", settings=SETTINGS
    )
    await _settle()

    assert comparison.status == "done"
    assert comparison.markdown == "the comparison"
    call = fake_backends["compare"][0]
    assert call["question"] == "Focus on cash"
    # One company was researched, so the comparison gets the business section.
    assert call["with_research"] is True
    assert any("Widgets." in m for m in call["summaries"])
    assert comparison.companies == [
        ("00445790", "COMPANY 00445790"),
        ("00989096", "COMPANY 00989096"),
    ]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(analyses_router, "get_settings", lambda: SETTINGS)
    return TestClient(app)


def test_analyse_endpoint_starts_a_run(client, fake_backends):
    resp = client.post(
        "/analyses/company",
        json={"company_number": "00445790", "transaction_ids": ["t-2024"], "research": False},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["company_number"] == "00445790"

    read = client.get(f"/analyses/company/{body['id']}")
    assert read.status_code == 200
    assert read.json()["id"] == body["id"]

    assert client.get("/analyses/company/nope").status_code == 404


def test_analyse_endpoint_caps_years(client, fake_backends):
    resp = client.post(
        "/analyses/company",
        json={"company_number": "00445790", "transaction_ids": ["a", "b", "c", "d", "e"]},
    )
    assert resp.status_code == 422


def test_compare_endpoint_requires_two_finished_analyses(client, fake_backends):
    first = client.post(
        "/analyses/company",
        json={"company_number": "00445790", "transaction_ids": ["t-2024"]},
    ).json()
    second = client.post(
        "/analyses/company",
        json={"company_number": "00989096", "transaction_ids": ["t-2024"]},
    ).json()

    assert (
        client.post("/analyses/compare", json={"analysis_ids": [first["id"]]}).status_code
        == 422
    )
    assert (
        client.post(
            "/analyses/compare", json={"analysis_ids": [first["id"], first["id"]]}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/analyses/compare", json={"analysis_ids": [first["id"], "missing"]}
        ).status_code
        == 404
    )

    resp = client.post(
        "/analyses/compare",
        json={"analysis_ids": [first["id"], second["id"]], "guidance": "Cash"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert [c["company_number"] for c in body["companies"]] == ["00445790", "00989096"]
    assert client.get(f"/analyses/compare/{body['id']}").status_code == 200
    assert client.get("/analyses/compare/nope").status_code == 404


def test_compare_rejects_an_unfinished_analysis(client, monkeypatch, fake_backends):
    unfinished = CompanyAnalysis(id="pending1", company_number="00445790", status="running")
    monkeypatch.setitem(analysis_jobs._analyses, "pending1", unfinished)
    done = client.post(
        "/analyses/company",
        json={"company_number": "00989096", "transaction_ids": ["t-2024"]},
    ).json()

    resp = client.post(
        "/analyses/compare", json={"analysis_ids": ["pending1", done["id"]]}
    )
    assert resp.status_code == 409
    assert "not finished" in resp.json()["detail"]
