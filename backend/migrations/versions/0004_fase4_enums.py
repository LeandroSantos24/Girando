"""Fase 4: valores nuevos de enums (carrocería, cuentas comerciales, publicidad, eventos).

Revision ID: 0004
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlfiles import run_sql  # noqa: E402

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql("0004_fase4_enums.sql")


def downgrade() -> None:
    raise RuntimeError("Sin downgrade automático: restaurar desde backup.")
