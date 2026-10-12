from pathlib import Path

import pytest

from mcpkb.config import ROOT, Settings
from mcpkb.sampledata import build_sample_db


@pytest.fixture(scope="session")
def db_path(tmp_path_factory) -> Path:
    return build_sample_db(tmp_path_factory.mktemp("db") / "shop.db")


@pytest.fixture
def settings(db_path) -> Settings:
    return Settings(docs_dir=ROOT / "data" / "docs", db_path=db_path, sql_timeout=1.0, max_rows=100)
