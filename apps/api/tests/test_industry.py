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


def test_industry_refinement_adds_documents_and_threads(client, isolated_store, monkeypatch):
    """The revision reads the original uploads plus the new ones."""
    seen: list[dict] = []

    async def fake_refine(**kwargs):
        seen.append(
            {
                "documents": [d.filename for d in kwargs["documents"]],
                "new": kwargs["new_filenames"],
                "previous": kwargs["previous"],
                "instruction": kwargs["instruction"],
            }
        )
        return AnalysisResult(markdown="## Summary\nRevised.", model="claude-test")

    monkeypatch.setattr(analysis_jobs, "refine_industry", fake_refine)

    first = client.post(
        "/industry",
        data={"title": "UK EdTech", "prompt": "Size the market."},
        files=[("files", ("review.pdf", b"%PDF-1.4 one", "application/pdf"))],
    ).json()

    revision = client.post(
        f"/industry/{first['id']}/refine",
        data={"instruction": "Now focus on funding routes."},
        files=[("files", ("funding.pdf", b"%PDF-1.4 two", "application/pdf"))],
    )
    assert revision.status_code == 202
    body = revision.json()
    assert body["parent_id"] == first["id"]
    assert body["root_id"] == first["id"]
    assert body["instruction"] == "Now focus on funding routes."

    call = seen[0]
    assert sorted(call["documents"]) == ["funding.pdf", "review.pdf"]
    assert call["new"] == ["funding.pdf"]
    assert call["previous"] == "## Summary\nUK EdTech reviewed."

    thread = client.get(f"/industry/{first['id']}/thread").json()
    assert [a["id"] for a in thread] == [first["id"], body["id"]]
    # The library shows the head with its revision count, not both rows.
    listing = client.get("/analyses").json()
    assert [i["id"] for i in listing] == [first["id"]]
    assert listing[0]["revisions"] == 2


def test_industry_refinement_without_new_documents_still_reads_the_originals(
    client, isolated_store, monkeypatch
):
    seen: list[list[str]] = []

    async def fake_refine(**kwargs):
        seen.append([d.filename for d in kwargs["documents"]])
        return AnalysisResult(markdown="Revised.", model="claude-test")

    monkeypatch.setattr(analysis_jobs, "refine_industry", fake_refine)
    first = client.post(
        "/industry",
        data={"title": "UK EdTech"},
        files=[("files", ("review.pdf", b"%PDF one", "application/pdf"))],
    ).json()

    resp = client.post(
        f"/industry/{first['id']}/refine", data={"instruction": "Shorter please."}
    )
    assert resp.status_code == 202
    assert seen[0] == ["review.pdf"]


def test_refining_rejects_a_blank_instruction_or_unfinished_analysis(client, isolated_store):
    first = client.post(
        "/industry",
        data={"title": "UK EdTech"},
        files=[("files", ("review.pdf", b"%PDF", "application/pdf"))],
    ).json()
    assert (
        client.post(
            f"/industry/{first['id']}/refine", data={"instruction": "  "}
        ).status_code
        == 400
    )
    assert (
        client.post("/industry/nope/refine", data={"instruction": "more"}).status_code
        == 404
    )


def test_deleting_the_head_removes_the_uploaded_documents(client, isolated_store):
    from app.services.document_store import get_document_store

    first = client.post(
        "/industry",
        data={"title": "UK EdTech"},
        files=[("files", ("review.pdf", b"%PDF", "application/pdf"))],
    ).json()
    assert get_document_store().load_all(first["id"]) != []

    assert client.delete(f"/industry/{first['id']}").status_code == 204
    assert get_document_store().load_all(first["id"]) == []
