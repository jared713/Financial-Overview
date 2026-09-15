"""Durable storage for finished analyses and comparisons.

SQLite in a single file, because the API already has to run as one replica and
this is a handful of rows per session — a Postgres service would be a second
thing to pay for and operate for no gain. Point `DATA_DIR` at a Railway volume
and the file survives redeploys; without one it lands in the container's
filesystem and is lost on the next deploy, which `/companies/features` reports
so the UI can say so.

Runs are saved when they finish, successfully or not, and are kept until
someone deletes them.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any

from app.services.analysis_models import AnalysedFilingRef, CompanyAnalysis, Comparison

log = logging.getLogger("financial-overview.store")

SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    company_number TEXT NOT NULL,
    company_name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    research INTEGER NOT NULL DEFAULT 0,
    filings TEXT NOT NULL DEFAULT '[]',
    markdown TEXT,
    error TEXT,
    research_markdown TEXT,
    research_error TEXT,
    ownership_markdown TEXT,
    ownership_error TEXT,
    model TEXT,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS analyses_created_at ON analyses (created_at DESC);

CREATE TABLE IF NOT EXISTS comparisons (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    status TEXT NOT NULL,
    guidance TEXT,
    analysis_ids TEXT NOT NULL DEFAULT '[]',
    companies TEXT NOT NULL DEFAULT '[]',
    markdown TEXT,
    error TEXT,
    model TEXT,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS comparisons_created_at ON comparisons (created_at DESC);
"""


class Store:
    def __init__(self, path: Path, durable: bool = True):
        self.path = path
        self.durable = durable
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # WAL keeps the reader (the library listing) off the writer's back.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._add_missing_columns()
        self._conn.commit()

    def _add_missing_columns(self) -> None:
        """CREATE TABLE IF NOT EXISTS leaves an older file on its old shape, so
        add any column the schema has gained since. Cheap enough to run always."""
        wanted = {
            "analyses": {
                "research_markdown": "TEXT",
                "research_error": "TEXT",
                "ownership_markdown": "TEXT",
                "ownership_error": "TEXT",
            }
        }
        for table, columns in wanted.items():
            existing = {
                row["name"] for row in self._conn.execute(f"PRAGMA table_info({table})")
            }
            for name, kind in columns.items():
                if name not in existing:
                    log.info("Adding column %s.%s", table, name)
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")

    # --- writes -------------------------------------------------------

    def save_analysis(self, analysis: CompanyAnalysis) -> None:
        filings = json.dumps([vars(f) for f in analysis.filings])
        with self._lock:
            self._conn.execute(
                """INSERT INTO analyses (id, created_at, company_number, company_name,
                       status, research, filings, markdown, error, research_markdown,
                       research_error, ownership_markdown, ownership_error, model,
                       input_tokens, output_tokens)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                       company_name=excluded.company_name, status=excluded.status,
                       filings=excluded.filings, markdown=excluded.markdown,
                       error=excluded.error, research_markdown=excluded.research_markdown,
                       research_error=excluded.research_error,
                       ownership_markdown=excluded.ownership_markdown,
                       ownership_error=excluded.ownership_error, model=excluded.model,
                       input_tokens=excluded.input_tokens,
                       output_tokens=excluded.output_tokens""",
                (
                    analysis.id,
                    analysis.created_at,
                    analysis.company_number,
                    analysis.company_name,
                    analysis.status,
                    int(analysis.research),
                    filings,
                    analysis.markdown,
                    analysis.error,
                    analysis.research_markdown,
                    analysis.research_error,
                    analysis.ownership_markdown,
                    analysis.ownership_error,
                    analysis.model,
                    analysis.input_tokens,
                    analysis.output_tokens,
                ),
            )
            self._conn.commit()

    def save_comparison(self, comparison: Comparison) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO comparisons (id, created_at, status, guidance, analysis_ids,
                       companies, markdown, error, model, input_tokens, output_tokens)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                       status=excluded.status, markdown=excluded.markdown,
                       error=excluded.error, model=excluded.model,
                       input_tokens=excluded.input_tokens,
                       output_tokens=excluded.output_tokens""",
                (
                    comparison.id,
                    comparison.created_at,
                    comparison.status,
                    comparison.guidance,
                    json.dumps(comparison.analysis_ids),
                    json.dumps([list(c) for c in comparison.companies]),
                    comparison.markdown,
                    comparison.error,
                    comparison.model,
                    comparison.input_tokens,
                    comparison.output_tokens,
                ),
            )
            self._conn.commit()

    def delete_analysis(self, analysis_id: str) -> bool:
        with self._lock:
            cursor = self._conn.execute("DELETE FROM analyses WHERE id = ?", (analysis_id,))
            self._conn.commit()
            return cursor.rowcount > 0

    def delete_comparison(self, comparison_id: str) -> bool:
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM comparisons WHERE id = ?", (comparison_id,)
            )
            self._conn.commit()
            return cursor.rowcount > 0

    # --- reads --------------------------------------------------------

    def get_analysis(self, analysis_id: str) -> CompanyAnalysis | None:
        row = self._conn.execute(
            "SELECT * FROM analyses WHERE id = ?", (analysis_id,)
        ).fetchone()
        return _analysis_from_row(row) if row else None

    def get_comparison(self, comparison_id: str) -> Comparison | None:
        row = self._conn.execute(
            "SELECT * FROM comparisons WHERE id = ?", (comparison_id,)
        ).fetchone()
        return _comparison_from_row(row) if row else None

    def list_saved(self, limit: int = 200) -> list[dict[str, Any]]:
        """Everything saved, newest first, without the markdown bodies."""
        items: list[dict[str, Any]] = []
        for row in self._conn.execute(
            """SELECT id, created_at, company_number, company_name, status, research
               FROM analyses ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ):
            items.append(
                {
                    "kind": "analysis",
                    "id": row["id"],
                    "created_at": row["created_at"],
                    "title": row["company_name"] or row["company_number"],
                    "subtitle": row["company_number"],
                    "status": row["status"],
                    "research": bool(row["research"]),
                }
            )
        for row in self._conn.execute(
            """SELECT id, created_at, status, companies FROM comparisons
               ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ):
            names = [name for _, name in json.loads(row["companies"] or "[]")]
            items.append(
                {
                    "kind": "comparison",
                    "id": row["id"],
                    "created_at": row["created_at"],
                    "title": f"Comparison of {len(names)}" if names else "Comparison",
                    "subtitle": " · ".join(names),
                    "status": row["status"],
                    "research": False,
                }
            )
        items.sort(key=lambda item: item["created_at"], reverse=True)
        return items[:limit]


def _analysis_from_row(row: sqlite3.Row) -> CompanyAnalysis:
    return CompanyAnalysis(
        id=row["id"],
        created_at=row["created_at"],
        company_number=row["company_number"],
        company_name=row["company_name"],
        status=row["status"],
        research=bool(row["research"]),
        filings=[AnalysedFilingRef(**f) for f in json.loads(row["filings"] or "[]")],
        markdown=row["markdown"],
        error=row["error"],
        research_markdown=row["research_markdown"],
        research_error=row["research_error"],
        ownership_markdown=row["ownership_markdown"],
        ownership_error=row["ownership_error"],
        model=row["model"],
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
    )


def _comparison_from_row(row: sqlite3.Row) -> Comparison:
    return Comparison(
        id=row["id"],
        created_at=row["created_at"],
        status=row["status"],
        guidance=row["guidance"],
        analysis_ids=json.loads(row["analysis_ids"] or "[]"),
        companies=[tuple(c) for c in json.loads(row["companies"] or "[]")],
        markdown=row["markdown"],
        error=row["error"],
        model=row["model"],
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
    )


_store: Store | None = None


def get_store() -> Store:
    """Open the store once, falling back to a non-durable location if the
    configured directory cannot be written (no volume attached, say)."""
    global _store
    if _store is not None:
        return _store

    from app.config import get_settings

    settings = get_settings()
    directory = Path(settings.data_dir)
    durable = True
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".writable"
        probe.touch()
        probe.unlink()
    except OSError as e:
        log.warning(
            "DATA_DIR %s is not writable (%s) — saving to /tmp instead, which is lost "
            "on redeploy. Attach a Railway volume mounted at %s to keep results.",
            directory,
            e,
            directory,
        )
        directory = Path("/tmp/financial-overview")
        directory.mkdir(parents=True, exist_ok=True)
        durable = False

    _store = Store(directory / "financial-overview.sqlite3", durable=durable)
    log.info("Store open at %s (durable=%s)", _store.path, durable)
    return _store
