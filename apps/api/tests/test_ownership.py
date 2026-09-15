from app.services.companies_house import Filing, FilingDocument
from app.services.ownership import build_ownership_content, summarise_psc


def test_summarise_psc_flattens_the_fields_that_matter():
    summary = summarise_psc(
        {
            "items": [
                {
                    "name": "Jane Holder",
                    "kind": "individual-person-with-significant-control",
                    "natures_of_control": [
                        "ownership-of-shares-50-to-75-percent",
                        "voting-rights-50-to-75-percent",
                    ],
                    "notified_on": "2017-04-06",
                    "nationality": "British",
                    "country_of_residence": "England",
                },
                {
                    "name": "HOLDCO LIMITED",
                    "kind": "corporate-entity-person-with-significant-control",
                    "natures_of_control": ["ownership-of-shares-75-to-100-percent"],
                    "notified_on": "2020-01-01",
                    "ceased_on": "2023-06-30",
                    "identification": {
                        "registration_number": "09876543",
                        "legal_authority": "England",
                    },
                },
            ]
        },
        {"items": []},
    )
    assert "Jane Holder (individual person with significant control)" in summary
    assert "ownership of shares 50 to 75 percent" in summary
    assert "voting rights 50 to 75 percent" in summary
    assert "notified on: 2017-04-06" in summary
    assert "nationality: British" in summary
    # A ceased corporate holder is flagged, with the number needed to follow it up.
    assert "CEASED on: 2023-06-30" in summary
    assert "registration number: 09876543" in summary


def test_summarise_psc_explains_an_empty_register():
    summary = summarise_psc(
        {"items": []},
        {
            "items": [
                {
                    "statement": "psc-exempt-as-trading-on-regulated-market",
                    "notified_on": "2016-06-30",
                }
            ]
        },
    )
    assert "no active entries" in summary
    assert "psc exempt as trading on regulated market" in summary


def test_summarise_psc_survives_a_sparse_entry():
    assert "unnamed" in summarise_psc({"items": [{}]}, {"items": []})


def _doc(txn: str, description: str, date: str) -> FilingDocument:
    return FilingDocument(
        filing=Filing(
            transaction_id=txn, date=date, type="CS01", description=description,
            made_up_to=None,
        ),
        content=b"%PDF-1.4 fake",
    )


def test_build_ownership_content_labels_each_document():
    content = build_ownership_content(
        company_name="ACME LTD",
        company_number="00000001",
        psc_summary="- Jane Holder",
        documents=[_doc("c1", "confirmation-statement", "2024-06-01")],
    )
    assert [b["type"] for b in content] == ["text", "text", "document", "text"]
    assert "00000001" in content[0]["text"]
    assert "Jane Holder" in content[0]["text"]
    assert "confirmation-statement" in content[1]["text"]
    assert "2024-06-01" in content[1]["text"]
    assert content[2]["source"]["media_type"] == "application/pdf"
    assert "## Shareholders" in content[-1]["text"]


def test_build_ownership_content_says_when_nothing_was_downloadable():
    content = build_ownership_content(
        company_name="ACME LTD",
        company_number="00000001",
        psc_summary="- none",
        documents=[],
    )
    assert any("No confirmation statement" in b.get("text", "") for b in content)
