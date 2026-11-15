"""Fase 4: mensajería general, publicidad medida, recomendaciones e historial.

Revision ID: 0007
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlfiles import run_sql  # noqa: E402

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql("0007_fase4_mensajes_publicidad.sql")


def downgrade() -> None:
    raise RuntimeError("Sin downgrade automático: restaurar desde backup.")
