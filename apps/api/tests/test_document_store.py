import pytest

from app.services.document_store import DocumentStore, safe_name


@pytest.fixture
def documents(tmp_path):
    return DocumentStore(tmp_path / "documents")


def test_safe_name_strips_paths_and_separators():
    assert safe_name("../../etc/passwd") == "passwd"
    assert safe_name("DfE review 2025.pdf") == "DfE-review-2025.pdf"
    assert safe_name("/absolute/report.pdf") == "report.pdf"
    assert safe_name("...") == "document"
    assert safe_name("") == "document"
    assert len(safe_name("x" * 400)) <= 120


def test_round_trips_documents_for_a_thread(documents):
    documents.save("root1", "review.pdf", b"%PDF one")
    documents.save("root1", "notes.md", b"# notes")
    loaded = dict(documents.load_all("root1"))
    assert loaded["review.pdf"] == b"%PDF one"
    assert loaded["notes.md"] == b"# notes"


def test_a_repeat_filename_is_kept_alongside_rather_than_overwritten(documents):
    first = documents.save("root1", "review.pdf", b"first")
    second = documents.save("root1", "review.pdf", b"second")
    assert first != second
    contents = {content for _, content in documents.load_all("root1")}
    assert contents == {b"first", b"second"}


def test_threads_do_not_see_each_other(documents):
    documents.save("root1", "a.pdf", b"a")
    documents.save("root2", "b.pdf", b"b")
    assert [n for n, _ in documents.load_all("root1")] == ["a.pdf"]
    assert [n for n, _ in documents.load_all("root2")] == ["b.pdf"]


def test_unknown_thread_reads_as_empty(documents):
    assert documents.load_all("nothing-here") == []


def test_delete_removes_the_whole_thread(documents):
    documents.save("root1", "a.pdf", b"a")
    documents.delete("root1")
    assert documents.load_all("root1") == []
    documents.delete("root1")  # idempotent


def test_a_traversing_root_id_cannot_escape_the_folder(documents):
    documents.save("../escape", "a.pdf", b"a")
    assert (documents.root / "escape").is_dir()
    assert not (documents.root.parent / "escape").exists()
