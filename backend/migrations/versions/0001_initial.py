"""Modelo de datos v0 aprobado (enums, tablas, triggers, RLS, vistas públicas, estadísticas).

Revision ID: 0001
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlfiles import run_sql  # noqa: E402

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql("0001_initial")


def downgrade() -> None:
    raise RuntimeError("La migración inicial no se revierte: restaurar desde backup.")
