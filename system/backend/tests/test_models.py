from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import CheckConstraint, DateTime, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from app.models import Base, DocumentChunk, ProductPrice
from scripts.seed_demo_data import DEMO_PRODUCTS

TABLES = {'users', 'products', 'product_prices', 'documents', 'document_permissions',
          'document_products', 'document_chunks', 'conversations', 'messages', 'audit_logs'}


def test_ten_tables_and_timezone():
    assert set(Base.metadata.tables) == TABLES
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, DateTime):
                assert column.type.timezone
        assert not table.c.created_at.nullable


def test_vector_metadata_and_decimal():
    assert DocumentChunk.__table__.c.embedding.type.dim == 512
    assert not DocumentChunk.__table__.c.embedding.nullable
    assert isinstance(DocumentChunk.__table__.c.metadata.type, JSONB)
    price = ProductPrice.__table__.c.price.type
    assert isinstance(price, Numeric) and (price.precision, price.scale) == (12, 2)
    assert price.asdecimal
    assert all(not index.dialect_options['postgresql'].get('using') for t in Base.metadata.tables.values() for index in t.indexes)


def test_unique_and_foreign_keys():
    expected = {'products': {'brand', 'model'}, 'document_permissions': {'document_id', 'role'},
                'document_chunks': {'document_id', 'chunk_index'}}
    for name, fields in expected.items():
        assert any(isinstance(c, UniqueConstraint) and set(c.columns.keys()) == fields
                   for c in Base.metadata.tables[name].constraints)
    for name in ('document_permissions', 'document_products', 'document_chunks'):
        fk = next(iter(Base.metadata.tables[name].c.document_id.foreign_keys))
        assert fk.ondelete == 'CASCADE'
    assert next(iter(Base.metadata.tables['audit_logs'].c.user_id.foreign_keys)).ondelete == 'SET NULL'


def test_status_checks_and_demo_boundaries():
    for name in ('users', 'products', 'product_prices', 'documents', 'document_permissions', 'messages', 'audit_logs'):
        assert any(isinstance(c, CheckConstraint) for c in Base.metadata.tables[name].constraints)
    assert len(DEMO_PRODUCTS) == 3
    assert len({(p['brand'], p['model']) for p in DEMO_PRODUCTS}) == 3
    assert {p['model'] for p in DEMO_PRODUCTS} == {'X100', 'X200', 'Y200'}


def test_offline_upgrade_and_downgrade(monkeypatch):
    # Offline SQL compilation is not a live database migration test.
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://localhost/product_agent')
    output = StringIO()
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'), output_buffer=output)
    command.upgrade(config, 'head', sql=True)
    sql = output.getvalue()
    assert 'CREATE EXTENSION IF NOT EXISTS vector;' in sql
    for table in TABLES:
        assert f'CREATE TABLE {table} (' in sql
    assert 'VECTOR(1536)' in sql
    assert 'ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(512)' in sql
    assert 'document_chunks is not empty' in sql
    output.truncate(0)
    output.seek(0)
    command.downgrade(config, '0001_foundation:base', sql=True)
    sql = output.getvalue()
    for table in TABLES:
        assert f'DROP TABLE {table};' in sql
    assert 'DROP EXTENSION' not in sql
