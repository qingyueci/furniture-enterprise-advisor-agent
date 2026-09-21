from alembic import context

from app.core.config import Settings
from app.core.database import get_engine
from app.models import Base

if context.is_offline_mode():
    context.configure(url=Settings().database_url.get_secret_value(), target_metadata=Base.metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()
else:
    with get_engine().connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
