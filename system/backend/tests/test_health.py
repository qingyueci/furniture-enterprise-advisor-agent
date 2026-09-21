import asyncio
import logging
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.database import get_engine
from app.main import app, lifespan


@pytest.fixture
def engine():
    mock = MagicMock()
    app.dependency_overrides[get_engine] = lambda: mock
    yield mock
    app.dependency_overrides.clear()


def test_health_ok(engine):
    engine.connect.return_value.__enter__.return_value.scalar.return_value = True
    with TestClient(app) as client:
        response = client.get('/api/health')
    assert response.status_code == 200
    assert response.json() == {
        'status': 'ok', 'application': 'enterprise-product-analysis-agent',
        'database': 'ok', 'pgvector': 'ok',
    }


def test_health_missing_vector(engine):
    engine.connect.return_value.__enter__.return_value.scalar.return_value = False
    with TestClient(app) as client:
        response = client.get('/api/health')
    assert response.status_code == 503
    assert response.json()['database'] == 'ok'
    assert response.json()['pgvector'] == 'missing'


@pytest.mark.parametrize('failure_at', ['connect', 'execute', 'scalar'])
def test_health_database_error_is_sanitized(engine, failure_at):
    error = OperationalError('SELECT private', {}, Exception('password=secret postgresql://private C:/private'))
    if failure_at == 'connect':
        engine.connect.side_effect = error
    else:
        getattr(engine.connect.return_value.__enter__.return_value, failure_at).side_effect = error
    with TestClient(app) as client:
        response = client.get('/api/health')
    assert response.status_code == 503
    assert response.json() == {
        'status': 'degraded', 'application': 'enterprise-product-analysis-agent',
        'database': 'error', 'pgvector': 'unknown',
    }
    assert all(secret not in response.text for secret in ('secret', 'SELECT', 'private', 'C:/'))


def test_health_is_preserved_with_auth_routes():
    with TestClient(app) as client:
        assert client.get('/api/health').json() == {
            'status': 'ok', 'application': 'enterprise-product-analysis-agent',
            'database': 'ok', 'pgvector': 'ok',
        }


def test_stale_document_recovery_failure_is_safely_logged(monkeypatch, caplog):
    error = OperationalError('SELECT private', {}, Exception('password=secret postgresql://private C:/private'))
    monkeypatch.setattr('app.main.mark_stale_parsing_failed', MagicMock(side_effect=error))

    async def run_lifespan():
        async with lifespan(app):
            return None

    with caplog.at_level(logging.WARNING, logger='app.main'):
        asyncio.run(run_lifespan())

    assert 'STALE_DOCUMENT_RECOVERY_FAILED error_code=DATABASE_ERROR' in caplog.text
    assert all(secret not in caplog.text for secret in ('password', 'secret', 'SELECT', 'private', 'C:/'))
