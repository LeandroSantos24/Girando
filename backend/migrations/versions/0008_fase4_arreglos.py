"""Fase 4: arreglo de la recursión RLS en messages y de la verificación de casas de repuestos.

Revision ID: 0008
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlfiles import run_sql  # noqa: E402

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql("0008_fase4_arreglos.sql")


def downgrade() -> None:
    raise RuntimeError("Sin downgrade automático: restaurar desde backup.")
