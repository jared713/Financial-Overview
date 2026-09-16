import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.routers import industry as industry_router
from app.services import analysis_jobs
from app.services.filing_analysis import AnalysisResult, FilingAnalysisError
from app.services.industry import (
    DEFAULT_PROMPT,
    UploadedDocument,
    build_industry_content,
    validate_documents,
)

SETTINGS = Settings(anthropic_api_key="sk-test", anthropic_model="claude-test")

PDF = UploadedDocument(filename="edtech-review.pdf", content=b"%PDF-1.4 fake", content_type="application/pdf")
TEXT = UploadedDocument(filename="notes.md", content=b"# Market notes\nGrowing.", content_type="text/markdown")


def test_pdfs_go_up_as_documents_and_text_as_text():
    content = build_industry_content(
        title="UK EdTech", prompt="Size the market.", documents=[PDF, TEXT]
    )
    kinds = [b["type"] for b in content]
    # header, (label, document), (label, text), instruction
    assert kinds == ["text", "text", "document", "text", "text", "text"]
    assert "UK EdTech" in content[0]["text"]
    assert "edtech-review.pdf" in content[1]["text"]
    assert content[2]["source"]["media_type"] == "application/pdf"
    assert "notes.md" in content[3]["text"]
    assert "# Market notes" in content[4]["text"]
    assert "Size the market." in content[-1]["text"]


def test_a_missing_prompt_falls_back_to_a_default_structure():
    content = build_industry_content(title="UK EdTech", prompt=None, documents=[PDF])
    instruction = content[-1]["text"]
    assert DEFAULT_PROMPT in instruction
    assert "Key figures" in instruction
    assert "Sources" in instruction


def test_a_given_prompt_does_not_get_the_fallback_structure():
    content = build_industry_content(
        title="UK EdTech", prompt="Just list the funding rounds.", documents=[PDF]
    )
    assert "Key figures" not in content[-1]["text"]


def test_validate_rejects_nothing_attached():
    with pytest.raises(FilingAnalysisError) as excinfo:
        validate_documents([])
    assert excinfo.value.status_code == 400


def test_validate_rejects_unsupported_formats():
    docx = UploadedDocument(
        filename="report.docx",
        content=b"PK\x03\x04",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    with pytest.raises(FilingAnalysisError) as excinfo:
        validate_documents([PDF, docx])
    assert "report.docx" in str(excinfo.value)
    assert "PDF" in str(excinfo.value)


def test_validate_rejects_too_many_and_too_large():
    with pytest.raises(FilingAnalysisError):
        validate_documents([PDF] * 9)

    huge = UploadedDocument(filename="big.pdf", content=b"x" * (21 * 1024 * 1024))
    with pytest.raises(FilingAnalysisError) as excinfo:
        validate_documents([huge])
    assert excinfo.value.status_code == 413


def test_validate_rejects_an_empty_file():
    with pytest.raises(FilingAnalysisError) as excinfo:
        validate_documents([UploadedDocument(filename="blank.pdf", content=b"")])
    assert "blank.pdf" in str(excinfo.value)


def test_content_type_is_not_required_to_spot_a_pdf():
    assert UploadedDocument(filename="x.PDF", content=b"%PDF").is_pdf
    assert UploadedDocument(filename="x.csv", content=b"a,b").is_text


@pytest.fixture
def client(monkeypatch):
    async def fake_analyse(**kwargs):
        return AnalysisResult(
            markdown=f"## Summary\n{kwargs['title']} reviewed.",
            model="claude-test",
            input_tokens=500,
            output_tokens=50,
        )

    monkeypatch.setattr(industry_router, "get_settings", lambda: SETTINGS)
    monkeypatch.setattr(analysis_jobs, "analyse_industry", fake_analyse)
    return TestClient(app)


def test_upload_starts_an_analysis_and_stores_the_result(client, isolated_store):
    resp = client.post(
        "/industry",
        data={"title": "UK EdTech", "prompt": "Size the market."},
        files=[
            ("files", ("review.pdf", b"%PDF-1.4 fake", "application/pdf")),
            ("files", ("notes.md", b"# notes", "text/markdown")),
        ],
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["title"] == "UK EdTech"
    assert [d["filename"] for d in body["documents"]] == ["review.pdf", "notes.md"]

    read = client.get(f"/industry/{body['id']}").json()
    assert read["markdown"] == "## Summary\nUK EdTech reviewed."
    # Kept, and listed alongside company work.
    listing = client.get("/analyses").json()
    assert [i["kind"] for i in listing] == ["industry"]
    assert listing[0]["title"] == "UK EdTech"

    assert client.delete(f"/industry/{body['id']}").status_code == 204
    assert client.get("/analyses").json() == []


def test_upload_rejects_an_unsupported_file_before_starting(client):
    resp = client.post(
        "/industry",
        data={"title": "UK EdTech"},
        files=[("files", ("report.docx", b"PK\x03\x04", "application/msword"))],
    )
    assert resp.status_code == 400
    assert "report.docx" in resp.json()["detail"]


def test_upload_requires_a_title(client):
    resp = client.post(
        "/industry",
        data={"title": "   "},
        files=[("files", ("review.pdf", b"%PDF", "application/pdf"))],
    )
    assert resp.status_code == 400


def test_missing_industry_analysis_is_404(client):
    assert client.get("/industry/nope").status_code == 404
    assert client.delete("/industry/nope").status_code == 404
