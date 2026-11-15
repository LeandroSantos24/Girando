"""Base única del esquema de Girando (fases 1 a 4 compactadas el 15/11/2026).

Aplica backend/sql/0001_base/*.sql en orden alfabético, dentro de una sola transacción.
Reemplaza a las versiones 0001–0009 anteriores; el esquema resultante es idéntico
(verificado con pg_dump --schema-only antes y después, ver docs/11-migraciones.md).

Revision ID: base_0001
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlfiles import run_sql  # noqa: E402

revision = "base_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql("0001_base")


def downgrade() -> None:
    raise RuntimeError("La base no se revierte: restaurar desde backup.")
