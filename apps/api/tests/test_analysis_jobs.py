import pytest

from app.config import Settings
from app.services import analysis_jobs
from app.services.analysis_jobs import (
    AnalysisJob,
    CompanyRun,
    Selection,
    _registered_office,
    _select_filings,
    create_job,
    run_job,
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
    selected = _select_filings(FILINGS, ["t-2024", "t-2022"])
    assert [f.transaction_id for f in selected] == ["t-2022", "t-2024"]


def test_select_filings_rejects_unknown_transaction():
    with pytest.raises(CompaniesHouseError) as excinfo:
        _select_filings(FILINGS, ["t-2024", "nope"])
    assert "nope" in str(excinfo.value)


def test_build_comparison_content_carries_each_review():
    blocks = build_comparison_content(
        [
            CompanySummary("00445790", "TESCO PLC", "## Filing\nTesco review"),
            CompanySummary("00989096", "J SAINSBURY PLC", "## Filing\nSainsbury review"),
        ],
        question="Which is growing faster?",
    )
    assert [b["type"] for b in blocks] == ["text", "text", "text", "text"]
    assert "TESCO PLC" in blocks[1]["text"]
    assert "Tesco review" in blocks[1]["text"]
    assert "J SAINSBURY PLC" in blocks[2]["text"]
    assert "Side by side" in blocks[-1]["text"]
    assert "Which is growing faster?" in blocks[-1]["text"]


class FakeClient:
    def __init__(self, api_key, **kwargs):
        pass

    async def list_account_filings(self, company_number, *, limit=50):
        return FILINGS

    async def get_company(self, company_number):
        return {"company_name": f"COMPANY {company_number}"}

    async def fetch_filing_documents(self, filings):
        return [FilingDocument(filing=f, content=b"%PDF-1.4 fake") for f in filings]


@pytest.fixture
def fake_backends(monkeypatch):
    calls = {"analyse": [], "compare": []}

    async def fake_analyse(documents, **kwargs):
        calls["analyse"].append(kwargs["company_number"])
        return AnalysisResult(
            markdown=f"review of {kwargs['company_name']}",
            model="claude-test",
            input_tokens=100,
            output_tokens=10,
        )

    async def fake_compare(summaries, **kwargs):
        calls["compare"].append([s.company_number for s in summaries])
        return AnalysisResult(
            markdown="the comparison", model="claude-test", input_tokens=50, output_tokens=5
        )

    monkeypatch.setattr(analysis_jobs, "CompaniesHouseClient", FakeClient)
    monkeypatch.setattr(analysis_jobs, "analyse_filings", fake_analyse)
    monkeypatch.setattr(analysis_jobs, "compare_companies", fake_compare)
    return calls


async def test_run_job_summarises_each_company_then_compares(fake_backends):
    selections = [
        Selection("00445790", ["t-2024", "t-2023"]),
        Selection("00989096", ["t-2024"]),
    ]
    job = create_job(selections, question="Who is stronger?")
    await run_job(job, selections, SETTINGS)

    assert job.status == "done"
    assert [c.status for c in job.companies] == ["done", "done"]
    assert job.companies[0].company_name == "COMPANY 00445790"
    assert job.companies[0].markdown == "review of COMPANY 00445790"
    assert [f.transaction_id for f in job.companies[0].filings] == ["t-2023", "t-2024"]
    assert job.comparison_markdown == "the comparison"
    assert fake_backends["compare"] == [["00445790", "00989096"]]
    # Two company calls plus the comparison.
    assert job.input_tokens == 250
    assert job.output_tokens == 25


async def test_single_company_run_skips_comparison(fake_backends):
    selections = [Selection("00445790", ["t-2024"])]
    job = create_job(selections, question=None)
    await run_job(job, selections, SETTINGS)

    assert job.status == "done"
    assert job.comparison_markdown is None
    assert job.comparison_error is None
    assert fake_backends["compare"] == []


async def test_one_failing_company_does_not_sink_the_run(monkeypatch, fake_backends):
    class HalfBrokenClient(FakeClient):
        async def list_account_filings(self, company_number, *, limit=50):
            if company_number == "99999999":
                raise CompaniesHouseError("Not found at Companies House", 404)
            return FILINGS

    monkeypatch.setattr(analysis_jobs, "CompaniesHouseClient", HalfBrokenClient)
    selections = [Selection("00445790", ["t-2024"]), Selection("99999999", ["t-2024"])]
    job = create_job(selections, question=None)
    await run_job(job, selections, SETTINGS)

    assert job.status == "done"
    assert job.companies[0].status == "done"
    assert job.companies[1].status == "error"
    assert "Not found" in (job.companies[1].error or "")
    # Only one company survived, so there is nothing to compare.
    assert job.comparison_markdown is None
    assert "Not enough companies" in (job.comparison_error or "")


async def test_job_reports_progress(fake_backends):
    selections = [Selection("00445790", ["t-2024"]), Selection("00989096", ["t-2024"])]
    job = AnalysisJob(
        id="x", companies=[CompanyRun(company_number=s.company_number) for s in selections]
    )
    assert job.finished_companies == 0
    await run_job(job, selections, SETTINGS)
    assert job.finished_companies == 2


def test_analyses_endpoints(monkeypatch):
    """POST starts a job and GET reads it back; no real work is run."""
    from fastapi.testclient import TestClient

    from app.main import app
    from app.routers import analyses as analyses_router

    started: list[tuple] = []

    def fake_start(selections, question, settings, research=False):
        started.append((selections, question, research))
        return create_job(selections, question, research)

    monkeypatch.setattr(analyses_router, "start_job", fake_start)
    monkeypatch.setattr(
        analyses_router, "get_settings", lambda: SETTINGS
    )
    client = TestClient(app)

    resp = client.post(
        "/analyses",
        json={
            "companies": [
                {"company_number": "00445790", "transaction_ids": ["t-2024"]},
                {"company_number": "00989096", "transaction_ids": ["t-2024", "t-2023"]},
            ],
            "question": "Who is stronger?",
            "research": True,
        },
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["total"] == 2
    assert body["finished"] == 0
    assert [c["company_number"] for c in body["companies"]] == ["00445790", "00989096"]
    selections, question, research = started[0]
    assert [(s.company_number, s.transaction_ids) for s in selections] == [
        ("00445790", ["t-2024"]),
        ("00989096", ["t-2024", "t-2023"]),
    ]
    assert question == "Who is stronger?"
    assert research is True
    assert body["research"] is True

    read = client.get(f"/analyses/{body['id']}")
    assert read.status_code == 200
    assert read.json()["id"] == body["id"]

    assert client.get("/analyses/does-not-exist").status_code == 404


def test_analyses_rejects_duplicate_company(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.routers import analyses as analyses_router

    monkeypatch.setattr(analyses_router, "get_settings", lambda: SETTINGS)
    client = TestClient(app)
    resp = client.post(
        "/analyses",
        json={
            "companies": [
                {"company_number": "00445790", "transaction_ids": ["t-2024"]},
                {"company_number": "00445790", "transaction_ids": ["t-2023"]},
            ]
        },
    )
    assert resp.status_code == 400
    assert "twice" in resp.json()["detail"]


def test_analyses_caps_company_count(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.routers import analyses as analyses_router

    monkeypatch.setattr(analyses_router, "get_settings", lambda: SETTINGS)
    client = TestClient(app)
    resp = client.post(
        "/analyses",
        json={
            "companies": [
                {"company_number": f"0000000{i}", "transaction_ids": ["t-2024"]}
                for i in range(6)
            ]
        },
    )
    assert resp.status_code == 422


def test_registered_office_joins_the_parts_that_exist():
    assert _registered_office(
        {"registered_office_address": {"address_line_1": "Tesco House",
                                       "locality": "Welwyn Garden City",
                                       "postal_code": "AL7 1GA"}}
    ) == "Tesco House, Welwyn Garden City, AL7 1GA"
    assert _registered_office({}) is None


def test_build_research_prompt_carries_identity_and_accounts():
    from app.services.company_research import build_research_prompt

    prompt = build_research_prompt(
        company_name="ONMO LIMITED",
        company_number="11563518",
        trading_name="Onmo",
        registered_office="1 Fore Street, London",
        sic_codes=["64191"],
        filings_review="## Filing\nSmall company accounts.",
    )
    assert "11563518" in prompt
    assert "Trading name: Onmo" in prompt
    assert "1 Fore Street, London" in prompt
    assert "64191" in prompt
    assert "Small company accounts." in prompt
    assert "## Revenue model" in prompt
    assert "## Recent news" in prompt


def test_build_research_prompt_without_optional_context():
    from app.services.company_research import build_research_prompt

    prompt = build_research_prompt(
        company_name="ACME LTD",
        company_number="00000001",
        trading_name=None,
        registered_office=None,
        sic_codes=[],
        filings_review=None,
    )
    assert "Trading name" not in prompt
    assert "SIC codes" not in prompt
    assert "## Sources" in prompt


async def test_research_runs_per_company_and_feeds_the_comparison(monkeypatch, fake_backends):
    researched: list[tuple[str, str | None]] = []

    async def fake_research(**kwargs):
        researched.append((kwargs["company_number"], kwargs["trading_name"]))
        return AnalysisResult(
            markdown="## Revenue model\nThey sell widgets.",
            model="claude-test",
            input_tokens=20,
            output_tokens=5,
        )

    compared: list[str] = []

    async def fake_compare(summaries, **kwargs):
        compared.extend(s.markdown for s in summaries)
        assert kwargs["with_research"] is True
        return AnalysisResult(markdown="the comparison", model="claude-test")

    monkeypatch.setattr(analysis_jobs, "research_company", fake_research)
    monkeypatch.setattr(analysis_jobs, "compare_companies", fake_compare)

    selections = [
        Selection("00445790", ["t-2024"], trading_name="Tesco"),
        Selection("00989096", ["t-2024"]),
    ]
    job = create_job(selections, question=None, research=True)
    await run_job(job, selections, SETTINGS)

    assert researched == [("00445790", "Tesco"), ("00989096", None)]
    assert job.companies[0].research_markdown == "## Revenue model\nThey sell widgets."
    # The comparison sees the research alongside the accounts review.
    assert all("They sell widgets." in m for m in compared)


async def test_research_failure_leaves_the_accounts_review_intact(monkeypatch, fake_backends):
    async def broken_research(**kwargs):
        raise FilingAnalysisError("Claude web research failed: boom", 502)

    monkeypatch.setattr(analysis_jobs, "research_company", broken_research)

    selections = [Selection("00445790", ["t-2024"])]
    job = create_job(selections, question=None, research=True)
    await run_job(job, selections, SETTINGS)

    run = job.companies[0]
    assert run.status == "done"
    assert run.markdown is not None
    assert run.research_markdown is None
    assert "boom" in (run.research_error or "")


async def test_research_is_skipped_when_not_requested(monkeypatch, fake_backends):
    async def fail(**kwargs):
        raise AssertionError("research should not run")

    monkeypatch.setattr(analysis_jobs, "research_company", fail)
    selections = [Selection("00445790", ["t-2024"])]
    job = create_job(selections, question=None, research=False)
    await run_job(job, selections, SETTINGS)
    assert job.companies[0].research_markdown is None
