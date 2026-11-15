"""Grants mínimos para la API y funciones auxiliares (conteo de favoritos, slug de agencia).

Revision ID: 0002
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlfiles import run_sql  # noqa: E402

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql("0002_api_grants.sql")


def downgrade() -> None:
    pass
