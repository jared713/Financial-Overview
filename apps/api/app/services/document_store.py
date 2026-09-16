"""Keep the documents uploaded for an industry analysis.

They used to be read into the request and dropped, which was fine while an
analysis was a single shot. Refinement changes that: asking for "the same, but
focused on funding" has to re-read the source, and "here are two more reports"
has to combine old and new. So the files are written next to the database,
under the thread's root id, and every revision in that thread reads the folder.

Files, not SQLite blobs: a 15MB PDF has no business in a row you select on, and
this way a backup is still a directory copy.
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

log = logging.getLogger("financial-overview.document_store")

# Uploaded names reach us from a browser, so they are rebuilt rather than
# trusted: no separators, no traversal, no surprises on disk.
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
MAX_NAME = 120


def safe_name(filename: str) -> str:
    stem = Path(filename).name or "document"
    cleaned = _SAFE.sub("-", stem).strip("-.") or "document"
    return cleaned[:MAX_NAME]


class DocumentStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _folder(self, root_id: str) -> Path:
        return self.root / safe_name(root_id)

    def save(self, root_id: str, filename: str, content: bytes) -> str:
        """Write one file, returning the name it was stored under.

        A repeat name is suffixed rather than overwritten — two reports can
        legitimately both be called `review.pdf`.
        """
        folder = self._folder(root_id)
        folder.mkdir(parents=True, exist_ok=True)
        name = safe_name(filename)
        target = folder / name
        if target.exists():
            stem, suffix = target.stem, target.suffix
            counter = 2
            while target.exists():
                target = folder / f"{stem}-{counter}{suffix}"
                counter += 1
        target.write_bytes(content)
        return target.name

    def load_all(self, root_id: str) -> list[tuple[str, bytes]]:
        """Every document in the thread, oldest first by write time."""
        folder = self._folder(root_id)
        if not folder.is_dir():
            return []
        files = sorted(
            (f for f in folder.iterdir() if f.is_file()), key=lambda f: f.stat().st_mtime
        )
        return [(f.name, f.read_bytes()) for f in files]

    def delete(self, root_id: str) -> None:
        folder = self._folder(root_id)
        if folder.is_dir():
            shutil.rmtree(folder, ignore_errors=True)


_documents: DocumentStore | None = None


def get_document_store() -> DocumentStore:
    global _documents
    if _documents is None:
        from app.services.store import get_store

        _documents = DocumentStore(get_store().path.parent / "documents")
        log.info("Document store at %s", _documents.root)
    return _documents
