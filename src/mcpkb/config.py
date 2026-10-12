import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _env(name: str, default: str) -> str:
    return os.environ.get(f"MCPKB_{name}", default)


@dataclass(frozen=True)
class Settings:
    docs_dir: Path = ROOT / "data" / "docs"
    db_path: Path = ROOT / "data" / "shop.db"
    inferq_url: str | None = None
    sql_timeout: float = 3.0
    max_rows: int = 100
    max_cell_chars: int = 500
    min_score: float = 5.0
    http_timeout: float = 5.0
    token: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            docs_dir=Path(_env("DOCS_DIR", str(cls.docs_dir))),
            db_path=Path(_env("DB_PATH", str(cls.db_path))),
            inferq_url=os.environ.get("MCPKB_INFERQ_URL") or None,
            sql_timeout=float(_env("SQL_TIMEOUT", str(cls.sql_timeout))),
            max_rows=int(_env("MAX_ROWS", str(cls.max_rows))),
            min_score=float(_env("MIN_SCORE", str(cls.min_score))),
            token=os.environ.get("MCPKB_TOKEN") or None,
        )
