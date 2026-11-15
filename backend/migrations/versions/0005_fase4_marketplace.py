"""Fase 4: marketplace: carrocería, color, precio normalizado y financiación por entidad.

Revision ID: 0005
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlfiles import run_sql  # noqa: E402

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql("0005_fase4_marketplace.sql")


def downgrade() -> None:
    raise RuntimeError("Sin downgrade automático: restaurar desde backup.")
