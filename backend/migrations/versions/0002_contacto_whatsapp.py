"""Contacto por WhatsApp: obligatorio para publicar, redirect sin exponer el número, aperturas por día,
precio al guardar un favorito y precio vs mercado.

Revision ID: 0002_contacto_whatsapp
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlfiles import run_sql  # noqa: E402

revision = "0002_contacto_whatsapp"
down_revision = "base_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql("0002_contacto_whatsapp.sql")


def downgrade() -> None:
    raise RuntimeError("No se revierte: restaurar desde backup.")
