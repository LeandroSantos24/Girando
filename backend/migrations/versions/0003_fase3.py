"""Fase 3: Admin vs Super Admin (RLS), períodos de suscripción por calendario, Home administrable,
verificación preparada (checklist/evidencia), tienda online de agencias y eventos de tracking.

Revision ID: 0003
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlfiles import run_sql  # noqa: E402

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql("0003_fase3.sql")


def downgrade() -> None:
    raise RuntimeError("Sin downgrade automático: restaurar desde backup.")
