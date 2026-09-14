from app.services.companies_house import (
    Filing,
    FilingDocument,
    _DocumentCache,
    document_id_from_metadata_url,
    parse_company_hit,
    parse_filing,
)
from app.services.filing_analysis import build_message_content

SEARCH_ITEM = {
    "company_number": "00445790",
    "title": "TESCO PLC",
    "company_status": "active",
    "company_type": "plc",
    "date_of_creation": "1947-11-27",
    "address_snippet": "Tesco House, Shire Park, Welwyn Garden City, AL7 1GA",
}

FILING_ITEM = {
    "transaction_id": "MzM1NjEyNzk3NGFkaXF6a2N4",
    "date": "2024-05-16",
    "type": "AA",
    "category": "accounts",
    "description": "accounts-with-accounts-type-group",
    "description_values": {"made_up_date": "2024-02-24"},
    "pages": 132,
    "paper_filed": False,
    "links": {
        "self": "/company/00445790/filing-history/MzM1NjEyNzk3NGFkaXF6a2N4",
        "document_metadata": (
            "https://document-api.company-information.service.gov.uk/document/abc-DEF_123"
        ),
    },
}


def test_parse_company_hit():
    hit = parse_company_hit(SEARCH_ITEM)
    assert hit.company_number == "00445790"
    assert hit.title == "TESCO PLC"
    assert hit.company_status == "active"


def test_parse_company_hit_tolerates_missing_fields():
    hit = parse_company_hit({})
    assert hit.company_number == ""
    assert hit.title == ""
    assert hit.company_status is None


def test_parse_filing_lifts_made_up_date_and_document_id():
    filing = parse_filing(FILING_ITEM)
    assert filing.transaction_id == "MzM1NjEyNzk3NGFkaXF6a2N4"
    assert filing.made_up_to == "2024-02-24"
    assert filing.document_id == "abc-DEF_123"
    assert filing.pages == 132
    assert filing.paper_filed is False


def test_parse_filing_without_document_is_not_downloadable():
    filing = parse_filing({"transaction_id": "x", "date": "1999-01-01", "links": {}})
    assert filing.document_id is None
    assert filing.made_up_to is None


def test_document_id_from_metadata_url():
    assert document_id_from_metadata_url("https://host/document/AB-12") == "AB-12"
    assert document_id_from_metadata_url("https://host/document/AB-12/") == "AB-12"
    assert document_id_from_metadata_url(None) is None


def test_document_cache_expires_and_bounds_itself():
    cache = _DocumentCache(ttl_seconds=0.0)
    cache.put("a", b"1234")
    assert cache.get("a") is None  # already expired

    bounded = _DocumentCache(ttl_seconds=60.0, max_bytes=8)
    bounded.put("a", b"1234")
    bounded.put("b", b"5678")
    bounded.put("c", b"90ab")
    assert sum(len(v.value) for v in bounded._entries.values()) <= 8
    bounded.put("huge", b"x" * 100)
    assert bounded.get("huge") is None


def _doc(transaction_id: str, made_up_to: str) -> FilingDocument:
    return FilingDocument(
        filing=Filing(
            transaction_id=transaction_id,
            date="2024-05-16",
            type="AA",
            description="accounts-with-accounts-type-full",
            made_up_to=made_up_to,
        ),
        content=b"%PDF-1.4 fake",
    )


def test_build_message_content_labels_each_pdf():
    content = build_message_content(
        [_doc("t1", "2024-02-24"), _doc("t2", "2023-02-25")],
        company_name="TESCO PLC",
        company_number="00445790",
    )
    kinds = [block["type"] for block in content]
    # header, (label, document) * 2, instructions
    assert kinds == ["text", "text", "document", "text", "document", "text"]
    assert "2024-02-24" in content[1]["text"]
    assert content[2]["source"]["media_type"] == "application/pdf"
    assert "Trend table" in content[-1]["text"]


def test_build_message_content_single_filing_uses_summary_prompt():
    content = build_message_content(
        [_doc("t1", "2024-02-24")], company_name="TESCO PLC", company_number="00445790"
    )
    assert "Key figures" in content[-1]["text"]
    assert "Trend table" not in content[-1]["text"]


def test_build_message_content_appends_question():
    content = build_message_content(
        [_doc("t1", "2024-02-24")],
        company_name="TESCO PLC",
        company_number="00445790",
        question="What are the director loans?",
    )
    assert "What are the director loans?" in content[-1]["text"]


def test_filing_document_filename_uses_period_end():
    assert _doc("t1", "2024-02-24").filename == "accounts-2024-02-24.pdf"
