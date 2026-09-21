from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.config import get_settings
from app.core.database import get_engine
from app.main import app
from app.models import User
from app.security.jwt import create_access_token, decode_access_token
from app.security.passwords import hash_password, verify_password


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
    for name, role, status in (("admin", "ADMIN", "ACTIVE"), ("pm", "PRODUCT_MANAGER", "ACTIVE"),
                               ("sales", "SALES", "ACTIVE"), ("disabled", "SALES", "DISABLED")):
        password = f"Test-{name}-{suffix}!"
        user = User(username=f"{name}_{suffix}", password_hash=hash_password(password), role=role, status=status)
        database_session.add(user)
        database_session.flush()
        result[name] = (user, password)
    return result


def login(client, user, password):
    response = client.post("/api/auth/login", json={"username": user.username.upper(), "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_password_argon2id():
    password_hash = hash_password("valid-password")
    assert password_hash != "valid-password"
    assert password_hash.startswith("$argon2id$")
    assert verify_password("valid-password", password_hash)
    assert not verify_password("incorrect-password", password_hash)


def test_jwt_claims_and_tamper(client, users):
    user, password = users["sales"]
    token = login(client, user, password)
    claims = decode_access_token(token)
    assert claims["sub"] == str(user.id) and claims["username"] == user.username and claims["role"] == "SALES"
    header, payload, signature = token.split(".")
    bad_signature = ("a" if signature[0] != "a" else "b") + signature[1:]
    bad_token = f"{header}.{payload}.{bad_signature}"
    response = client.get("/api/auth/me", headers=bearer(bad_token))
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "AUTH_TOKEN_INVALID"


def test_expired_and_invalid_sub_are_unauthorized(client, users):
    user, _ = users["sales"]
    secret = get_settings().jwt_secret.get_secret_value()
    now = datetime.now(timezone.utc)
    expired = jwt.encode({"sub": str(user.id), "username": user.username, "role": user.role, "ver": 0,
                          "iat": now - timedelta(minutes=2), "exp": now - timedelta(minutes=1)}, secret, algorithm="HS256")
    invalid_sub = jwt.encode({"sub": "not-a-uuid", "username": user.username, "role": user.role, "ver": 0,
                              "iat": now, "exp": now + timedelta(minutes=1)}, secret, algorithm="HS256")
    assert client.get("/api/auth/me", headers=bearer(expired)).json()["error"]["code"] == "AUTH_TOKEN_EXPIRED"
    assert client.get("/api/auth/me", headers=bearer(invalid_sub)).json()["error"]["code"] == "AUTH_TOKEN_INVALID"


def test_three_roles_login_and_me_without_secrets(client, users):
    for name, expected_role in (("admin", "ADMIN"), ("pm", "PRODUCT_MANAGER"), ("sales", "SALES")):
        user, password = users[name]
        response = client.post("/api/auth/login", json={"username": f"  {user.username.upper()}  ", "password": password})
        body = response.json()
        assert response.status_code == 200
        assert body["success"] and body["data"]["expires_in"] == 1800
        assert body["data"]["user"]["role"] == expected_role
        assert not ({"password", "password_hash", "token_version"} & body["data"]["user"].keys())
        me = client.get("/api/auth/me", headers=bearer(body["data"]["access_token"]))
        assert me.status_code == 200 and me.json()["data"]["username"] == user.username
        assert "X-Request-ID" in me.headers
        assert database_user_last_login(client, user.id) is not None


def database_user_last_login(client, user_id):
    # The test fixture's same session sees the committed nested transaction.
    return app.dependency_overrides[get_db]().get(User, user_id).last_login_at


def test_invalid_credentials_disabled_and_missing_token(client, users):
    user, password = users["sales"]
    for payload in ({"username": "missing_user", "password": password}, {"username": user.username, "password": "incorrect-password"}):
        response = client.post("/api/auth/login", json=payload)
        assert response.status_code == 401 and response.json()["error"] == {
            "code": "AUTH_INVALID_CREDENTIALS", "message": "用户名或密码错误", "details": None,
        }
    disabled, disabled_password = users["disabled"]
    assert client.post("/api/auth/login", json={"username": disabled.username, "password": disabled_password}).status_code == 403
    response = client.get("/api/auth/me")
    assert response.status_code == 401 and response.json()["error"]["code"] == "AUTH_TOKEN_MISSING"


def test_logout_and_version_mismatch_invalidate_token(client, users, database_session):
    user, password = users["sales"]
    token = login(client, user, password)
    assert client.post("/api/auth/logout", headers=bearer(token)).status_code == 200
    assert client.get("/api/auth/me", headers=bearer(token)).json()["error"]["code"] == "AUTH_TOKEN_INVALID"
    token = login(client, user, password)
    database_session.get(User, user.id).token_version += 1
    database_session.commit()
    assert client.get("/api/auth/me", headers=bearer(token)).status_code == 401


def test_disabled_and_role_changed_users_use_database_state(client, users, database_session):
    user, password = users["sales"]
    token = login(client, user, password)
    database_session.get(User, user.id).status = "DISABLED"
    database_session.commit()
    assert client.get("/api/auth/me", headers=bearer(token)).json()["error"]["code"] == "ACCOUNT_DISABLED"
    admin, admin_password = users["admin"]
    admin_token = login(client, admin, admin_password)
    database_session.get(User, admin.id).role = "SALES"
    database_session.commit()
    response = client.get("/api/users", headers=bearer(admin_token))
    assert response.status_code == 403 and response.json()["error"]["code"] == "PERMISSION_DENIED"


def test_user_management_permissions_and_pagination(client, users):
    admin, admin_password = users["admin"]
    token = login(client, admin, admin_password)
    for key in ("pm", "sales"):
        user, password = users[key]
        assert client.get("/api/users", headers=bearer(login(client, user, password))).status_code == 403
    response = client.get("/api/users", params={"keyword": users["sales"][0].username, "role": "SALES", "status": "ACTIVE", "page": 1, "page_size": 1}, headers=bearer(token))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["pagination"]["page_size"] == 1 and data["pagination"]["total"] == 1
    assert data["items"][0]["username"] == users["sales"][0].username


def test_create_update_and_last_active_admin_guard(client, users, database_session):
    admin, admin_password = users["admin"]
    token = login(client, admin, admin_password)
    unique = uuid4().hex[:12]
    created = client.post("/api/users", headers=bearer(token), json={"username": f"new_{unique}", "password": "Created-user-password", "role": "SALES", "status": "ACTIVE"})
    assert created.status_code == 201
    created_data = created.json()["data"]
    assert not ({"password_hash", "token_version"} & created_data.keys())
    assert client.post("/api/users", headers=bearer(token), json={"username": f"new_{unique}", "password": "Created-user-password", "role": "SALES", "status": "ACTIVE"}).json()["error"]["code"] == "USERNAME_EXISTS"
    target_id = created_data["id"]
    changed = client.put(f"/api/users/{target_id}", headers=bearer(token), json={"role": "PRODUCT_MANAGER", "new_password": "Changed-user-password"})
    assert changed.status_code == 200 and changed.json()["data"]["role"] == "PRODUCT_MANAGER"
    for other_admin in database_session.scalars(select(User).where(User.role == "ADMIN", User.status == "ACTIVE", User.id != admin.id)):
        other_admin.status = "DISABLED"
    database_session.commit()
    assert client.put(f"/api/users/{admin.id}", headers=bearer(token), json={"status": "DISABLED"}).json()["error"]["code"] == "LAST_ACTIVE_ADMIN_REQUIRED"


def test_user_validation_and_token_invalidation_on_update(client, users):
    admin, admin_password = users["admin"]
    sales, sales_password = users["sales"]
    admin_token = login(client, admin, admin_password)
    sales_token = login(client, sales, sales_password)
    assert client.post("/api/users", headers=bearer(admin_token), json={"username": "bad", "password": "short", "role": "BAD", "status": "BAD"}).status_code == 422
    assert client.put(f"/api/users/{sales.id}", headers=bearer(admin_token), json={}).status_code == 422
    assert client.put(f"/api/users/{sales.id}", headers=bearer(admin_token), json={"status": "DISABLED"}).status_code == 200
    assert client.get("/api/auth/me", headers=bearer(sales_token)).status_code == 401
