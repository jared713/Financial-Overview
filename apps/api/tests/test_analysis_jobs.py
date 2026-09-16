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
    # The web write-up leads; the filed accounts follow.
    assert summary.markdown.index("They sell groceries.") < summary.markdown.index(
        "Accounts review."
    )
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

    async def get_persons_with_significant_control(self, company_number):
        return {
            "items": [
                {
                    "name": "Jane Holder",
                    "kind": "individual-person-with-significant-control",
                    "natures_of_control": ["ownership-of-shares-50-to-75-percent"],
                    "notified_on": "2017-04-06",
                }
            ]
        }

    async def get_psc_statements(self, company_number):
        return {"items": []}

    async def list_ownership_filings(self, company_number):
        return [_filing("cs-2024", "2024-06-01", "2024-05-31")]


@pytest.fixture
def fake_backends(monkeypatch):
    calls: dict[str, list] = {
        "analyse": [],
        "research": [],
        "ownership": [],
        "compare": [],
    }

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

    async def fake_ownership(**kwargs):
        calls["ownership"].append(kwargs["company_number"])
        return AnalysisResult(
            markdown="## Shareholders\nJane Holder, 60%.",
            model="claude-test",
            input_tokens=30,
            output_tokens=6,
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
    monkeypatch.setattr(analysis_jobs, "analyse_ownership", fake_ownership)
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
    # Accounts review plus the ownership pass.
    assert analysis.input_tokens == 130
    assert analysis.ownership_markdown == "## Shareholders\nJane Holder, 60%."
    assert fake_backends["ownership"] == ["00445790"]
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
    # Accounts + research + ownership.
    assert analysis.input_tokens == 150


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


async def test_finished_analysis_is_saved_and_readable_after_the_cache_is_cleared(
    fake_backends, isolated_store
):
    from app.services.analysis_jobs import _analyses, get_analysis

    analysis = start_analysis(
        company_number="00445790",
        transaction_ids=["t-2024"],
        trading_name=None,
        research=False,
        settings=SETTINGS,
    )
    await _settle()

    assert isolated_store.get_analysis(analysis.id) is not None
    _analyses.clear()  # as if the process restarted
    restored = get_analysis(analysis.id)
    assert restored is not None
    assert restored.markdown == "review of COMPANY 00445790"


async def test_failed_analysis_is_saved_too(fake_backends, isolated_store):
    analysis = start_analysis(
        company_number="99999999",
        transaction_ids=["t-2024"],
        trading_name=None,
        research=False,
        settings=SETTINGS,
    )
    await _settle()

    saved = isolated_store.get_analysis(analysis.id)
    assert saved is not None and saved.status == "error"


def test_library_endpoints_list_and_delete(client, fake_backends, isolated_store):
    from app.services.analysis_models import CompanyAnalysis as Stored

    isolated_store.save_analysis(
        Stored(id="kept", company_number="00445790", company_name="TESCO PLC", status="done")
    )
    listing = client.get("/analyses").json()
    assert [i["id"] for i in listing] == ["kept"]
    assert listing[0]["kind"] == "analysis"

    assert client.delete("/analyses/company/kept").status_code == 204
    assert client.get("/analyses").json() == []
    assert client.delete("/analyses/company/kept").status_code == 404


def test_saved_analysis_is_readable_through_the_api(client, isolated_store):
    from app.services.analysis_models import CompanyAnalysis as Stored

    isolated_store.save_analysis(
        Stored(id="old", company_number="00445790", status="done", markdown="from disk")
    )
    body = client.get("/analyses/company/old").json()
    assert body["markdown"] == "from disk"


async def test_ownership_failure_leaves_the_rest_of_the_analysis_intact(
    monkeypatch, fake_backends
):
    async def broken(**kwargs):
        raise FilingAnalysisError("psc unavailable")

    monkeypatch.setattr(analysis_jobs, "analyse_ownership", broken)
    analysis = start_analysis(
        company_number="00445790",
        transaction_ids=["t-2024"],
        trading_name=None,
        research=False,
        settings=SETTINGS,
    )
    await _settle()

    assert analysis.status == "done"
    assert analysis.markdown is not None
    assert analysis.ownership_markdown is None
    assert "psc unavailable" in (analysis.ownership_error or "")


async def test_ownership_reaches_the_comparison(fake_backends):
    first = start_analysis(
        company_number="00445790",
        transaction_ids=["t-2024"],
        trading_name=None,
        research=False,
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
    start_comparison(analyses=[first, second], guidance=None, settings=SETTINGS)
    await _settle()

    summaries = fake_backends["compare"][0]["summaries"]
    assert all("Jane Holder, 60%." in s for s in summaries)


async def test_refinement_forms_a_thread_and_re_reads_the_filings(
    monkeypatch, fake_backends
):
    refinements: list[dict] = []

    async def fake_refine(documents, **kwargs):
        refinements.append(
            {
                "filings": [d.filing.transaction_id for d in documents],
                "previous": kwargs["previous"],
                "instruction": kwargs["instruction"],
            }
        )
        return AnalysisResult(markdown="revised review", model="claude-test")

    monkeypatch.setattr(analysis_jobs, "refine_filings_review", fake_refine)

    original = start_analysis(
        company_number="00445790",
        transaction_ids=["t-2024", "t-2023"],
        trading_name=None,
        research=False,
        settings=SETTINGS,
    )
    await _settle()

    revision = analysis_jobs.start_company_refinement(
        previous=original, instruction="Say more about the debt", settings=SETTINGS
    )
    await _settle()

    assert revision.status == "done"
    assert revision.markdown == "revised review"
    assert revision.parent_id == original.id
    assert revision.root_id == original.root_id == original.id
    assert revision.instruction == "Say more about the debt"
    # The same filings are re-read, and the previous review is handed over.
    assert refinements[0]["filings"] == ["t-2023", "t-2024"]
    assert refinements[0]["previous"] == original.markdown

    thread = analysis_jobs.company_thread(original.root_id)
    assert [a.id for a in thread] == [original.id, revision.id]


async def test_refining_a_refinement_stays_in_the_same_thread(monkeypatch, fake_backends):
    async def fake_refine(documents, **kwargs):
        return AnalysisResult(markdown=f"revision of: {kwargs['previous']}", model="t")

    monkeypatch.setattr(analysis_jobs, "refine_filings_review", fake_refine)
    original = start_analysis(
        company_number="00445790",
        transaction_ids=["t-2024"],
        trading_name=None,
        research=False,
        settings=SETTINGS,
    )
    await _settle()
    first = analysis_jobs.start_company_refinement(
        previous=original, instruction="More on cash", settings=SETTINGS
    )
    await _settle()
    second = analysis_jobs.start_company_refinement(
        previous=first, instruction="Now shorter", settings=SETTINGS
    )
    await _settle()

    assert second.parent_id == first.id
    assert second.root_id == original.id
    # Each revision builds on the one before, not on the original.
    assert second.markdown == f"revision of: {first.markdown}"
    assert [a.id for a in analysis_jobs.company_thread(original.id)] == [
        original.id,
        first.id,
        second.id,
    ]


def test_refine_endpoint_rejects_an_unfinished_or_missing_analysis(client, fake_backends):
    from app.services.analysis_models import CompanyAnalysis as Stored

    running = Stored(id="running1", company_number="00445790", status="running")
    analysis_jobs._analyses["running1"] = running
    try:
        assert (
            client.post(
                "/analyses/company/running1/refine", json={"instruction": "more"}
            ).status_code
            == 409
        )
        assert (
            client.post(
                "/analyses/company/nope/refine", json={"instruction": "more"}
            ).status_code
            == 404
        )
    finally:
        analysis_jobs._analyses.pop("running1", None)


def test_refine_endpoint_requires_an_instruction(client, fake_backends, isolated_store):
    from app.services.analysis_models import CompanyAnalysis as Stored

    isolated_store.save_analysis(
        Stored(id="done1", company_number="00445790", status="done", markdown="x")
    )
    resp = client.post("/analyses/company/done1/refine", json={"instruction": "  "})
    assert resp.status_code == 400
    assert client.post(
        "/analyses/company/done1/refine", json={"instruction": ""}
    ).status_code == 422


def test_thread_endpoint_returns_revisions_in_order(client, fake_backends, isolated_store):
    from app.services.analysis_models import CompanyAnalysis as Stored

    isolated_store.save_analysis(
        Stored(id="r1", company_number="00445790", status="done", created_at=1.0)
    )
    isolated_store.save_analysis(
        Stored(
            id="r2",
            parent_id="r1",
            root_id="r1",
            instruction="more",
            company_number="00445790",
            status="done",
            created_at=2.0,
        )
    )
    # Reachable from either end of the thread.
    for entry in ("r1", "r2"):
        thread = client.get(f"/analyses/company/{entry}/thread").json()
        assert [a["id"] for a in thread] == ["r1", "r2"]
        assert thread[1]["instruction"] == "more"

    # The library lists the head only, with the revision count.
    listing = client.get("/analyses").json()
    assert [i["id"] for i in listing] == ["r1"]
    assert listing[0]["revisions"] == 2
