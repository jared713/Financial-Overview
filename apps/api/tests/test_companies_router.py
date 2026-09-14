import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import companies as companies_router
from app.services.companies_house import Filing, FilingDocument
from app.services.filing_analysis import AnalysisResult

FILINGS = [
    Filing(
        transaction_id="t-2024",
        date="2024-05-16",
        type="AA",
        description="accounts-with-accounts-type-full",
        made_up_to="2024-02-24",
        document_id="doc-2024",
    ),
    Filing(
        transaction_id="t-2023",
        date="2023-05-12",
        type="AA",
        description="accounts-with-accounts-type-full",
        made_up_to="2023-02-25",
        document_id=None,  # no document available for download
    ),
]

PROFILE = {
    "company_number": "00445790",
    "company_name": "TESCO PLC",
    "company_status": "active",
    "type": "plc",
    "registered_office_address": {
        "address_line_1": "Tesco House",
        "locality": "Welwyn Garden City",
        "postal_code": "AL7 1GA",
    },
    "sic_codes": ["47110"],
    "accounts": {"last_accounts": {"made_up_to": "2024-02-24"}, "next_accounts": {}},
}


class FakeClient:
    async def search_companies(self, query, *, limit=20):
        return []

    async def get_company(self, company_number):
        return PROFILE

    async def list_account_filings(self, company_number, *, limit=50):
        return FILINGS

    async def fetch_filing_documents(self, filings):
        return [FilingDocument(filing=f, content=b"%PDF-1.4 fake") for f in filings]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(companies_router, "_client", lambda: FakeClient())
    return TestClient(app)


def test_list_filings_marks_undownloadable_filings(client):
    rows = client.get("/companies/00445790/filings").json()
    assert [r["transaction_id"] for r in rows] == ["t-2024", "t-2023"]
    assert rows[0]["downloadable"] is True
    assert rows[1]["downloadable"] is False
    assert rows[0]["made_up_to"] == "2024-02-24"


def test_company_profile_flattens_address(client):
    body = client.get("/companies/00445790").json()
    assert body["company_name"] == "TESCO PLC"
    assert body["registered_office"] == "Tesco House, Welwyn Garden City, AL7 1GA"
    assert body["accounts_last_made_up_to"] == "2024-02-24"


def test_download_pdf_streams_with_filename(client):
    resp = client.get("/companies/00445790/filings/t-2024/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "00445790-accounts-2024-02-24.pdf" in resp.headers["content-disposition"]
    assert resp.content == b"%PDF-1.4 fake"


def test_unknown_transaction_id_is_404(client):
    resp = client.get("/companies/00445790/filings/nope/pdf")
    assert resp.status_code == 404
    assert "nope" in resp.json()["detail"]


def test_analyse_returns_markdown_and_filing_manifest(client, monkeypatch):
    async def fake_analyse(documents, **kwargs):
        assert [d.filing.transaction_id for d in documents] == ["t-2024"]
        assert kwargs["company_name"] == "TESCO PLC"
        return AnalysisResult(
            markdown="## Filing\nLooks fine.", model="claude-test", input_tokens=10,
            output_tokens=20,
        )

    monkeypatch.setattr(companies_router, "analyse_filings", fake_analyse)
    resp = client.post("/companies/00445790/analyse", json={"transaction_ids": ["t-2024"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["markdown"].startswith("## Filing")
    assert body["model"] == "claude-test"
    assert body["filings"] == [
        {
            "transaction_id": "t-2024",
            "made_up_to": "2024-02-24",
            "date": "2024-05-16",
            "description": "accounts-with-accounts-type-full",
            "size_bytes": 13,
        }
    ]


def test_analyse_rejects_empty_selection(client):
    resp = client.post("/companies/00445790/analyse", json={"transaction_ids": []})
    assert resp.status_code == 422
