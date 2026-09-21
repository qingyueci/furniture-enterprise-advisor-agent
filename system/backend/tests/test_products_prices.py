from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.database import get_engine
from app.main import app
from app.models import Product, ProductPrice, User
from app.repositories.price_repository import PriceRepository
from app.security.passwords import hash_password


@pytest.fixture
def database_session():
    connection = get_engine().connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(database_session):
    app.dependency_overrides[get_db] = lambda: database_session
    with TestClient(app, base_url="http://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def users(database_session):
    suffix = uuid4().hex[:12]
    result = {}
    for label, role in (("admin", "ADMIN"), ("pm", "PRODUCT_MANAGER"), ("sales", "SALES")):
        password = f"Products-{label}-{suffix}!"
        user = User(username=f"products_{label}_{suffix}", password_hash=hash_password(password), role=role, status="ACTIVE")
        database_session.add(user)
        database_session.flush()
        result[label] = (user, password)
    return result


@pytest.fixture
def products(database_session):
    by_model = {product.model: product for product in database_session.scalars(select(Product))}
    assert {"X100", "X200", "Y200"} <= set(by_model)
    empty_product = Product(product_name="无价格测试产品", model=f"NO_PRICE_{uuid4().hex[:8]}", category=None,
                            brand="TEST_BRAND", product_type="INTERNAL", description="仅用于事务回滚测试")
    database_session.add(empty_product)
    database_session.flush()
    by_model["NO_PRICE"] = empty_product
    source = f"test-stage-03-{uuid4()}"
    timestamp = datetime(2030, 1, 1, tzinfo=timezone.utc)
    rows = [
        ("X100", "GUIDE", "3100.00", datetime(2029, 1, 1, tzinfo=timezone.utc)),
        ("X100", "GUIDE", "3199.00", timestamp),
        ("X100", "SALES", "2999.00", timestamp),
        ("X100", "SALES", "3099.00", timestamp),
        ("X100", "INTERNAL_QUOTE", "2699.00", timestamp),
        ("Y200", "GUIDE", "3499.00", timestamp),
        ("Y200", "SALES", "3299.00", timestamp),
    ]
    for model, price_type, price, update_time in rows:
        database_session.add(ProductPrice(product_id=by_model[model].id, price=Decimal(price), currency="CNY",
                                          price_type=price_type, source=source, update_time=update_time))
    database_session.flush()
    return by_model


def login(client, user, password):
    response = client.post("/api/auth/login", json={"username": user.username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def test_product_list_requires_login(client):
    response = client.get("/api/products")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_TOKEN_MISSING"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_all_roles_can_list_filter_and_page_products(client, users, products):
    for role in ("admin", "pm", "sales"):
        response = client.get("/api/products", headers=login(client, *users[role]))
        assert response.status_code == 200 and response.headers["X-Request-ID"]
    admin_headers = login(client, *users["admin"])
    response = client.get("/api/products", params={"keyword": "X", "brand": "DEMO_BRAND", "product_type": "INTERNAL", "page": 1, "page_size": 1}, headers=admin_headers)
    data = response.json()["data"]
    assert data["pagination"] == {"page": 1, "page_size": 1, "total": 2}
    assert data["items"][0]["model"] == "X100"
    assert client.get("/api/products", params={"product_type": "INVALID"}, headers=admin_headers).status_code == 422


def test_product_detail_and_not_found(client, users, products):
    headers = login(client, *users["sales"])
    response = client.get(f"/api/products/{products['X100'].id}", headers=headers)
    assert response.status_code == 200 and response.json()["data"]["model"] == "X100"
    missing = client.get("/api/products/999999999", headers=headers)
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


def test_visible_prices_roles_order_precision_and_tiebreak(client, users, products):
    expected = {
        "admin": ["GUIDE", "SALES", "INTERNAL_QUOTE"],
        "pm": ["GUIDE", "SALES", "INTERNAL_QUOTE"],
        "sales": ["GUIDE", "SALES"],
    }
    for role, price_types in expected.items():
        response = client.get(f"/api/products/{products['X100'].id}/price", headers=login(client, *users[role]))
        assert response.status_code == 200
        prices = response.json()["data"]["prices"]
        assert [price["price_type"] for price in prices] == price_types
        assert all(isinstance(price["price"], str) and price["price"].count(".") == 1 and len(price["price"].split(".")[1]) == 2 for price in prices)
        # The second same-time SALES insert has the larger id and must win.
        assert next(price for price in prices if price["price_type"] == "SALES")["price"] == "3099.00"


def test_internal_quote_permission_and_missing_types(client, users, products):
    sales_headers = login(client, *users["sales"])
    denied = client.get(f"/api/products/{products['X100'].id}/price", params={"price_type": "INTERNAL_QUOTE"}, headers=sales_headers)
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "PERMISSION_DENIED"
    for role in ("admin", "pm"):
        response = client.get(f"/api/products/{products['X100'].id}/price", params={"price_type": "INTERNAL_QUOTE"}, headers=login(client, *users[role]))
        assert response.status_code == 200 and response.json()["data"]["prices"][0]["price"] == "2699.00"
    y200 = client.get(f"/api/products/{products['Y200'].id}/price", headers=sales_headers)
    assert [price["price_type"] for price in y200.json()["data"]["prices"]] == ["GUIDE", "SALES"]
    no_price = client.get(f"/api/products/{products['NO_PRICE'].id}/price", headers=sales_headers)
    assert no_price.status_code == 404 and no_price.json()["error"]["code"] == "PRICE_NOT_FOUND"


def test_sales_sql_calls_exclude_internal_quote(client, users, products, monkeypatch):
    observed = []
    original = PriceRepository.latest_for_type

    def record(self, *args, **kwargs):
        observed.append(kwargs["price_type"])
        return original(self, *args, **kwargs)

    monkeypatch.setattr(PriceRepository, "latest_for_type", record)
    response = client.get(f"/api/products/{products['X100'].id}/price", headers=login(client, *users["sales"]))
    assert response.status_code == 200
    assert observed == ["GUIDE", "SALES"]


def test_price_validation_and_missing_product(client, users, products):
    headers = login(client, *users["admin"])
    assert client.get(f"/api/products/{products['X100'].id}/price", params={"price_type": "INVALID"}, headers=headers).status_code == 422
    missing = client.get("/api/products/999999999/price", headers=headers)
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "PRODUCT_NOT_FOUND"
