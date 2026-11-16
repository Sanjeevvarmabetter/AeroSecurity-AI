from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import create_engine

import app.models  # noqa: F401  (registers tables on metadata)
from app.core.config import get_settings
from app.models.base import Base

target_metadata = Base.metadata
URL = get_settings().database_url.get_secret_value()


def include_object(obj, name, type_, reflected, compare_to):  # type: ignore[no-untyped-def]
    # Only manage tables we own; PostGIS/tiger extension tables exist in the same schema.
    return not (type_ == "table" and reflected and compare_to is None)


def run_migrations_offline() -> None:
    context.configure(
        url=URL, target_metadata=target_metadata, literal_binds=True, include_object=include_object
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(URL, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
