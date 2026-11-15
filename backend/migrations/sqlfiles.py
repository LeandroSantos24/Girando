"""Ejecuta archivos .sql con el driver (sin interpretar ':' ni '%' como parámetros)."""
from pathlib import Path

from alembic import op

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"


def run_sql(*relative: str) -> None:
    raw = op.get_bind().connection.driver_connection  # psycopg.Connection
    for rel in relative:
        p = SQL_DIR / rel
        files = sorted(p.glob("*.sql")) if p.is_dir() else [p]
        for f in files:
            raw.execute(f.read_text(encoding="utf-8"))
