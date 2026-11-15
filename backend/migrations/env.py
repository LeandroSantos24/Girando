"""Alembic: migraciones SQL-first. El esquema aprobado vive en backend/sql/ y se aplica tal cual
(enums, constraints, triggers, RLS y vistas no se pueden expresar bien desde modelos ORM)."""
from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import get_settings

url = get_settings().database_owner_url


def run_migrations_online() -> None:
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None, transaction_per_migration=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    context.configure(url=url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    run_migrations_online()
