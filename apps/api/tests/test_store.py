import pytest

from app.services.analysis_models import AnalysedFilingRef, CompanyAnalysis, Comparison
from app.services.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "s.sqlite3")


def _analysis(**overrides) -> CompanyAnalysis:
    defaults = {
        "id": "a1",
        "company_number": "00445790",
        "company_name": "TESCO PLC",
        "status": "done",
        "research": True,
        "filings": [
            AnalysedFilingRef("t-2024", "2024-02-24", "2024-05-16", "accounts", 1234)
        ],
        "markdown": "## Filing\nReview.",
        "research_markdown": "## Revenue model\nGroceries.",
        "model": "claude-test",
        "input_tokens": 100,
        "output_tokens": 10,
    }
    return CompanyAnalysis(**{**defaults, **overrides})


def test_round_trips_an_analysis(store):
    store.save_analysis(_analysis())
    loaded = store.get_analysis("a1")
    assert loaded is not None
    assert loaded.company_name == "TESCO PLC"
    assert loaded.markdown == "## Filing\nReview."
    assert loaded.research_markdown == "## Revenue model\nGroceries."
    assert loaded.research is True
    assert loaded.input_tokens == 100
    assert [f.transaction_id for f in loaded.filings] == ["t-2024"]
    assert loaded.filings[0].size_bytes == 1234


def test_saving_the_same_id_updates_rather_than_duplicates(store):
    store.save_analysis(_analysis(status="running", markdown=None))
    store.save_analysis(_analysis(status="done", markdown="finished"))
    loaded = store.get_analysis("a1")
    assert loaded is not None and loaded.status == "done"
    assert loaded.markdown == "finished"
    assert len(store.list_saved()) == 1


def test_round_trips_a_comparison(store):
    store.save_comparison(
        Comparison(
            id="c1",
            analysis_ids=["a1", "a2"],
            status="done",
            guidance="Focus on cash",
            companies=[("00445790", "TESCO PLC"), ("00989096", "J SAINSBURY PLC")],
            markdown="## Side by side",
            model="claude-test",
        )
    )
    loaded = store.get_comparison("c1")
    assert loaded is not None
    assert loaded.analysis_ids == ["a1", "a2"]
    assert loaded.companies == [("00445790", "TESCO PLC"), ("00989096", "J SAINSBURY PLC")]
    assert loaded.guidance == "Focus on cash"


def test_missing_rows_read_as_none(store):
    assert store.get_analysis("nope") is None
    assert store.get_comparison("nope") is None


def test_list_saved_is_newest_first_and_describes_both_kinds(store):
    store.save_analysis(_analysis(id="a1", created_at=100.0))
    store.save_comparison(
        Comparison(
            id="c1",
            created_at=200.0,
            status="done",
            companies=[("1", "ONE LTD"), ("2", "TWO LTD")],
        )
    )
    store.save_analysis(_analysis(id="a2", created_at=300.0, company_name="THIRD LTD"))

    items = store.list_saved()
    assert [i["id"] for i in items] == ["a2", "c1", "a1"]
    assert items[0]["kind"] == "analysis"
    assert items[0]["title"] == "THIRD LTD"
    assert items[1]["kind"] == "comparison"
    assert items[1]["title"] == "Comparison of 2"
    assert items[1]["subtitle"] == "ONE LTD · TWO LTD"
    # Bodies are not carried in the listing.
    assert "markdown" not in items[0]


def test_delete_removes_and_reports_whether_it_existed(store):
    store.save_analysis(_analysis())
    assert store.delete_analysis("a1") is True
    assert store.get_analysis("a1") is None
    assert store.delete_analysis("a1") is False

    store.save_comparison(Comparison(id="c1", status="done"))
    assert store.delete_comparison("c1") is True
    assert store.delete_comparison("c1") is False


def test_survives_reopening_the_file(tmp_path):
    path = tmp_path / "keep.sqlite3"
    Store(path).save_analysis(_analysis())
    reopened = Store(path)
    assert reopened.get_analysis("a1") is not None


def test_round_trips_ownership(store):
    store.save_analysis(_analysis(ownership_markdown="## Shareholders\nJane, 60%."))
    loaded = store.get_analysis("a1")
    assert loaded is not None
    assert loaded.ownership_markdown == "## Shareholders\nJane, 60%."


def test_opens_a_file_created_before_the_ownership_columns_existed(tmp_path):
    """An older database must gain the new columns rather than fail to open."""
    import sqlite3

    path = tmp_path / "old.sqlite3"
    legacy = sqlite3.connect(path)
    legacy.execute(
        """CREATE TABLE analyses (
               id TEXT PRIMARY KEY, created_at REAL NOT NULL, company_number TEXT NOT NULL,
               company_name TEXT NOT NULL DEFAULT '', status TEXT NOT NULL,
               research INTEGER NOT NULL DEFAULT 0, filings TEXT NOT NULL DEFAULT '[]',
               markdown TEXT, error TEXT, model TEXT,
               input_tokens INTEGER NOT NULL DEFAULT 0,
               output_tokens INTEGER NOT NULL DEFAULT 0)"""
    )
    legacy.execute(
        "INSERT INTO analyses (id, created_at, company_number, status, markdown) "
        "VALUES ('old', 1.0, '00445790', 'done', 'kept')"
    )
    legacy.commit()
    legacy.close()

    upgraded = Store(path)
    restored = upgraded.get_analysis("old")
    assert restored is not None
    assert restored.markdown == "kept"
    assert restored.ownership_markdown is None

    upgraded.save_analysis(_analysis(id="new", ownership_markdown="## Shareholders"))
    assert upgraded.get_analysis("new").ownership_markdown == "## Shareholders"
