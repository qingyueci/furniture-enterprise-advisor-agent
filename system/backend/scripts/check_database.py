import json

from sqlalchemy import inspect, text

from app.core.database import get_engine
from app.models import Base


def check() -> dict:
    with get_engine().connect() as connection:
        tables = set(inspect(connection).get_table_names())
        expected = set(Base.metadata.tables)
        version = connection.scalar(text("SHOW server_version"))
        vector = connection.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
        missing = sorted(expected - tables)
        result = {"postgresql": version, "pgvector": vector,
                  "project_table_count": len(expected & tables), "missing_tables": missing}
        if missing or not vector or not version.startswith("16."):
            raise RuntimeError(json.dumps(result))
        return result


if __name__ == "__main__":
    print(json.dumps(check(), ensure_ascii=False))
