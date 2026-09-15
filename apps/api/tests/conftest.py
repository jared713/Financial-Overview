"""Keep tests off the real store: each run gets its own SQLite file."""

import pytest

from app.services import store as store_module


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    fresh = store_module.Store(tmp_path / "test.sqlite3", durable=True)
    monkeypatch.setattr(store_module, "_store", fresh)
    monkeypatch.setattr(store_module, "get_store", lambda: fresh)
    # Modules that imported get_store directly need the same object.
    from app.routers import companies as companies_router
    from app.services import analysis_jobs

    monkeypatch.setattr(analysis_jobs, "get_store", lambda: fresh)
    monkeypatch.setattr(companies_router, "get_store", lambda: fresh)
    yield fresh
