import io
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.api.documents import get_document_service
from app.core.database import get_engine
from app.main import app
from app.models import Document, DocumentChunk, DocumentPermission, DocumentProduct, Product, User
from app.rag.embeddings import FakeEmbeddingProvider
from app.repositories.document_repository import DocumentRepository
from app.security.passwords import hash_password
from app.services.document_service import DocumentService
from app.services.file_storage_service import FileStorageService
from app.services.knowledge_base_service import KnowledgeBaseService


def office_file(*names: str) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name in names:
            archive.writestr(name, b"demo")
    return stream.getvalue()


FILES = {
    "PDF": ("sample.pdf", b"%PDF-1.4\n% demo\n%%EOF", "application/pdf"),
    "DOCX": ("sample.docx", office_file("[Content_Types].xml", "word/document.xml"),
             "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "XLSX": ("sample.xlsx", office_file("[Content_Types].xml", "xl/workbook.xml"),
             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
}


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
def document_service(tmp_path):
    return DocumentService(storage=FileStorageService(tmp_path / "uploads", tmp_path / "temp"))


@pytest.fixture
def client(database_session, document_service):
    app.dependency_overrides[get_db] = lambda: database_session
    app.dependency_overrides[get_document_service] = lambda: document_service
    with TestClient(app, base_url="http://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def users(database_session):
    suffix = uuid4().hex[:10]
    result = {}
    for label, role in (("admin", "ADMIN"), ("pm", "PRODUCT_MANAGER"), ("sales", "SALES")):
        password = f"Docs-{label}-{suffix}!"
        user = User(username=f"docs_{label}_{suffix}", password_hash=hash_password(password), role=role, status="ACTIVE")
        database_session.add(user)
        database_session.flush()
        result[label] = (user, password)
    return result


@pytest.fixture
def product(database_session):
    item = database_session.scalar(select(Product).where(Product.model == "X100"))
    assert item is not None
    return item


def login(client, user_password):
    user, password = user_password
    response = client.post("/api/auth/login", json={"username": user.username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def upload(client, headers, file_data=FILES["PDF"], **overrides):
    product_id = overrides.pop("product_id", None)
    data = {
        "document_name": "X100 产品手册",
        "security_level": "INTERNAL",
        "allowed_roles": ["ADMIN", "PRODUCT_MANAGER"],
        "product_ids": [str(product_id)] if product_id is not None else [],
    }
    data.update(overrides)
    return client.post("/api/documents/upload", headers=headers,
                       files={"file": file_data}, data=data)


def test_authentication_and_upload_permission(client, users):
    assert client.get("/api/documents").status_code == 401
    denied = upload(client, login(client, users["sales"]))
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.parametrize("file_type", ["PDF", "DOCX", "XLSX"])
def test_admin_uploads_valid_formats_and_api_hides_paths(client, users, product, document_service, file_type):
    headers = login(client, users["admin"])
    response = upload(client, headers, FILES[file_type], product_id=product.id,
                      allowed_roles=["ADMIN", "PRODUCT_MANAGER", "PRODUCT_MANAGER"])
    assert response.status_code == 202
    result = response.json()["data"]
    assert result["file_type"] == file_type and result["parse_status"] == "PARSING"
    detail = client.get(f"/api/documents/{result['document_id']}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()["data"]
    assert body["product_ids"] == [product.id]
    assert body["allowed_roles"] == ["ADMIN", "PRODUCT_MANAGER"]
    assert "file_path" not in body and "checksum_sha256" not in body
    stored = list(document_service.storage.upload_dir.iterdir())
    assert len(stored) == 1 and stored[0].name != FILES[file_type][0]
    assert stored[0].parent.resolve() == document_service.storage.upload_dir


@pytest.mark.parametrize("file_data,expected", [
    (("empty.pdf", b"", "application/pdf"), "UNSUPPORTED_FILE_TYPE"),
    (("bad.txt", b"text", "text/plain"), "UNSUPPORTED_FILE_TYPE"),
    (("fake.pdf", b"not a pdf", "application/pdf"), "UNSUPPORTED_FILE_TYPE"),
    (("wrong.pdf", b"%PDF-1.4", "text/plain"), "UNSUPPORTED_FILE_TYPE"),
    (("macro.docx", office_file("[Content_Types].xml", "word/document.xml", "word/vbaProject.bin"),
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document"), "UNSUPPORTED_FILE_TYPE"),
    (("../escape.pdf", b"%PDF-1.4", "application/pdf"), "VALIDATION_ERROR"),
])
def test_rejects_unsafe_or_disguised_files(client, users, document_service, file_data, expected):
    response = upload(client, login(client, users["admin"]), file_data)
    assert response.status_code in {415, 422}
    assert response.json()["error"]["code"] == expected
    assert list(document_service.storage.upload_dir.iterdir()) == []
    assert list(document_service.storage.temp_dir.iterdir()) == []


def test_stream_limit_stops_upload_without_artifact(client, users, document_service):
    document_service.storage.max_bytes = 16
    response = upload(client, login(client, users["admin"]), ("large.pdf", b"%PDF-" + b"x" * 32, "application/pdf"))
    assert response.status_code == 413 and response.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert list(document_service.storage.upload_dir.iterdir()) == []


def test_product_validation_cleans_saved_file(client, users, document_service):
    response = upload(client, login(client, users["admin"]), product_id=999999999)
    assert response.status_code == 404 and response.json()["error"]["code"] == "PRODUCT_NOT_FOUND"
    assert list(document_service.storage.upload_dir.iterdir()) == []


def test_role_filtered_list_detail_download_and_immediate_permission_change(client, users, product):
    admin = login(client, users["admin"])
    pm = login(client, users["pm"])
    sales = login(client, users["sales"])
    response = upload(client, admin, product_id=product.id)
    document_id = response.json()["data"]["document_id"]

    assert client.get("/api/documents", headers=admin).json()["data"]["pagination"]["total"] >= 1
    assert any(item["id"] == document_id for item in client.get("/api/documents", headers=pm).json()["data"]["items"])
    assert all(item["id"] != document_id for item in client.get("/api/documents", headers=sales).json()["data"]["items"])
    assert client.get(f"/api/documents/{document_id}", headers=sales).status_code == 404
    assert client.get(f"/api/documents/{document_id}/download", headers=sales).status_code == 404

    granted = client.put(f"/api/documents/{document_id}/permissions", headers=admin,
                         json={"security_level": "INTERNAL", "allowed_roles": ["SALES"]})
    assert granted.status_code == 200 and granted.json()["data"]["allowed_roles"] == ["ADMIN", "SALES"]
    sales_detail = client.get(f"/api/documents/{document_id}", headers=sales)
    assert sales_detail.status_code == 200 and sales_detail.json()["data"]["allowed_roles"] is None
    download = client.get(f"/api/documents/{document_id}/download", headers=sales)
    assert download.status_code == 200 and download.content == FILES["PDF"][1]
    assert "sample.pdf" in download.headers["content-disposition"]

    revoked = client.put(f"/api/documents/{document_id}/permissions", headers=admin,
                         json={"security_level": "RESTRICTED", "allowed_roles": ["ADMIN"]})
    assert revoked.status_code == 200
    assert client.get(f"/api/documents/{document_id}", headers=sales).status_code == 404
    assert client.put(f"/api/documents/{document_id}/permissions", headers=sales,
                      json={"security_level": "INTERNAL", "allowed_roles": ["SALES"]}).status_code == 403
    assert client.delete(f"/api/documents/{document_id}", headers=sales).status_code == 403


def test_permission_api_revokes_removed_file_role_without_touching_source_public_chunk(
    client, users, database_session,
):
    """现有权限 API 同事务闭合文件层撤权与片段层历史引用鉴权。"""
    provider = FakeEmbeddingProvider()
    admin = users["admin"][0]
    sales = users["sales"][0]
    document = Document(
        document_name="分层授权回归.xlsx", original_name="分层授权回归.xlsx", file_type="XLSX",
        file_size=10, file_path="v11/layered-auth.xlsx", checksum_sha256="a" * 64,
        security_level="RESTRICTED", parse_status="READY", upload_user_id=admin.id,
    )
    database_session.add(document)
    database_session.flush()
    database_session.add_all([
        DocumentPermission(document_id=document.id, role="ADMIN"),
        DocumentPermission(document_id=document.id, role="PRODUCT_MANAGER"),
    ])
    chunk = DocumentChunk(
        document_id=document.id, chunk_index=0, chunk_text="公开片段：厨房防潮条件",
        section_title="产品实体", row_start=8, row_end=8, content_hash="b" * 64,
        chunk_metadata={
            "embedding_provider": provider.provider_name, "embedding_model": provider.model_name,
            "embedding_dimensions": provider.dimensions, "embedding_revision": provider.revision,
            "retrieval_roles": ["ADMIN", "PRODUCT_MANAGER", "SALES"],
        }, embedding=provider.embed_query("厨房防潮条件"),
    )
    database_session.add(chunk)
    database_session.commit()
    embedding_before = list(chunk.embedding)

    knowledge = KnowledgeBaseService(provider=provider)
    assert [item.chunk_id for item in knowledge.search(
        database_session, query="厨房防潮条件", current_user=sales, top_k=5,
    )] == [chunk.id]

    admin_headers = login(client, users["admin"])
    revoked = client.put(
        f"/api/documents/{document.id}/permissions", headers=admin_headers,
        json={"security_level": "RESTRICTED", "allowed_roles": ["ADMIN"]},
    )
    assert revoked.status_code == 200
    database_session.refresh(chunk)
    assert chunk.chunk_metadata["retrieval_revoked_roles"] == ["PRODUCT_MANAGER"]
    assert list(chunk.embedding) == embedding_before
    assert knowledge.search(database_session, query="厨房防潮条件", current_user=sales, top_k=5)

    # SALES is then explicitly granted at the file layer and removed through the
    # same API; the already-indexed retrieval-only chunk must become unavailable.
    database_session.add(DocumentPermission(document_id=document.id, role="SALES"))
    database_session.commit()
    revoked_again = client.put(
        f"/api/documents/{document.id}/permissions", headers=admin_headers,
        json={"security_level": "RESTRICTED", "allowed_roles": ["ADMIN"]},
    )
    assert revoked_again.status_code == 200
    database_session.refresh(chunk)
    assert chunk.chunk_metadata["retrieval_revoked_roles"] == ["PRODUCT_MANAGER", "SALES"]
    assert knowledge.search(database_session, query="厨房防潮条件", current_user=sales, top_k=5) == []


def test_non_admin_query_contains_permission_join():
    statement = DocumentRepository().list_query(role="SALES", keyword=None, file_type=None, parse_status=None, product_id=None)
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "document_permissions" in sql and "document_permissions.role = 'SALES'" in sql


def test_delete_removes_rows_and_exact_file(client, users, product, database_session, document_service):
    admin = login(client, users["admin"])
    response = upload(client, admin, product_id=product.id, allowed_roles=["ADMIN", "SALES"])
    document_id = response.json()["data"]["document_id"]
    document = database_session.get(Document, document_id)
    stored_path = Path(document.file_path)
    assert stored_path.is_file()
    deleted = client.delete(f"/api/documents/{document_id}", headers=admin)
    assert deleted.status_code == 204 and deleted.content == b""
    assert not stored_path.exists()
    assert database_session.get(Document, document_id) is None
    assert database_session.scalar(select(func.count()).select_from(DocumentPermission).where(
        DocumentPermission.document_id == document_id)) == 0
    assert database_session.scalar(select(func.count()).select_from(DocumentProduct).where(
        DocumentProduct.document_id == document_id)) == 0


def test_database_failure_during_upload_leaves_no_file(client, users, document_service, monkeypatch):
    def fail(*_args, **_kwargs):
        raise SQLAlchemyError("simulated")

    monkeypatch.setattr(document_service.documents, "products_exist", fail)
    response = upload(client, login(client, users["admin"]))
    assert response.status_code == 503 and response.json()["error"]["code"] == "DATABASE_ERROR"
    assert list(document_service.storage.upload_dir.iterdir()) == []
    assert "simulated" not in response.text


def test_storage_failure_is_sanitized(client, users, document_service, monkeypatch):
    async def fail(_upload):
        from app.core.exceptions import AppError
        raise AppError(500, "FILE_STORAGE_ERROR", "文件存储操作未完成")

    monkeypatch.setattr(document_service.storage, "save_upload", fail)
    response = upload(client, login(client, users["admin"]))
    assert response.status_code == 500
    assert response.json()["error"] == {"code": "FILE_STORAGE_ERROR", "message": "文件存储操作未完成", "details": None}


def test_delete_database_failure_restores_file(client, users, database_session, document_service, monkeypatch):
    admin = login(client, users["admin"])
    response = upload(client, admin)
    document_id = response.json()["data"]["document_id"]
    stored_path = Path(database_session.get(Document, document_id).file_path)
    assert stored_path.is_file()

    def fail_commit():
        raise SQLAlchemyError("simulated delete failure")

    monkeypatch.setattr(database_session, "commit", fail_commit)
    failed = client.delete(f"/api/documents/{document_id}", headers=admin)
    assert failed.status_code == 503 and failed.json()["error"]["code"] == "DATABASE_ERROR"
    assert stored_path.is_file()
    assert "simulated delete failure" not in failed.text
