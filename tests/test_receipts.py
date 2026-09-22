import asyncio
from datetime import date
from io import BytesIO
import json
import time

import httpx
import pytest
from PIL import Image

from app.common.exceptions import AppException
from app.core import config
from app.receipts import ocr_client
from app.receipts import service as receipt_service


def image_bytes(format_name: str) -> bytes:
    """작은 정상 이미지 합성 fixture. 외부 영수증 원본은 사용하지 않는다."""
    output = BytesIO()
    Image.new("RGB", (4, 4), color=(255, 255, 255)).save(output, format=format_name)
    return output.getvalue()


PNG_BYTES = image_bytes("PNG")
JPEG_BYTES = image_bytes("JPEG")
WEBP_BYTES = image_bytes("WEBP")


def auth_headers(client, email="owner@example.com"):
    response = client.post(
        "/auth/register",
        json={"email": email, "password": "correct-password", "name": email},
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def successful_result(vendor="테스트 상점", amount=4500.0, day=date(2026, 9, 15)):
    return ocr_client.OcrResult(
        vendor=vendor,
        amount=amount,
        date=day,
        ocr_raw=f"{vendor}\n{amount:g}\n{day.isoformat()}",
    )


def test_upload_success_persists_receipt_and_private_file(client, monkeypatch):
    headers = auth_headers(client)
    async def fake_extract(*_args):
        return successful_result()

    monkeypatch.setattr(ocr_client, "extract_receipt", fake_extract)
    response = client.post(
        "/receipts",
        headers=headers,
        files={"file": ("receipt.png", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "done"
    assert body["vendor"] == "테스트 상점"
    assert body["amount"] == 4500
    assert body["date"] == "2026-09-15"
    assert body["ocr_raw"] == "테스트 상점\n4500\n2026-09-15"
    assert body["image_url"].startswith("receipts/")
    stored = receipt_service.storage.root / body["image_url"]
    assert stored.is_file()
    assert stored.read_bytes() == PNG_BYTES

    detail = client.get(f"/receipts/{body['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json() == body

    listing = client.get("/receipts", headers=headers)
    assert listing.status_code == 200
    assert listing.json()[0]["id"] == body["id"]
    assert "image_url" not in listing.json()[0]


def test_upload_success_accepts_valid_jpeg(client, monkeypatch):
    headers = auth_headers(client)

    async def fake_extract(*_args):
        return successful_result()

    monkeypatch.setattr(ocr_client, "extract_receipt", fake_extract)
    response = client.post(
        "/receipts",
        headers=headers,
        files={"file": ("receipt.jpg", JPEG_BYTES, "image/jpeg")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "done"
    assert body["image_url"].endswith(".jpg")
    assert (receipt_service.storage.root / body["image_url"]).read_bytes() == JPEG_BYTES


def test_ocr_failure_creates_failed_receipt_with_null_extracted_fields(client, monkeypatch):
    headers = auth_headers(client)

    async def fake_extract(*_args):
        return None

    monkeypatch.setattr(ocr_client, "extract_receipt", fake_extract)
    response = client.post(
        "/receipts",
        headers=headers,
        files={"file": ("receipt.png", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "failed"
    assert body["ocr_raw"] is None
    assert body["vendor"] is None
    assert body["amount"] is None
    assert body["date"] is None
    assert (receipt_service.storage.root / body["image_url"]).is_file()


@pytest.mark.parametrize(
    ("filename", "content", "content_type"),
    [
        ("receipt.txt", b"not-an-image", "text/plain"),
        ("receipt.png", b"", "image/png"),
        ("receipt.png", b"\x00\x01\x02", "image/png"),
        ("receipt.png", b"\x89PNG\r\n\x1a\nnot-a-real-image", "image/png"),
        ("receipt.png", PNG_BYTES[:20], "image/png"),
    ],
)
def test_invalid_file_is_400(client, filename, content, content_type):
    headers = auth_headers(client)
    response = client.post(
        "/receipts",
        headers=headers,
        files={"file": (filename, content, content_type)},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_invalid_image_does_not_call_ocr_or_create_file_or_receipt(client, monkeypatch):
    headers = auth_headers(client)
    called = False

    async def unexpected_ocr(*_args):
        nonlocal called
        called = True
        return successful_result()

    monkeypatch.setattr(ocr_client, "extract_receipt", unexpected_ocr)
    response = client.post(
        "/receipts",
        headers=headers,
        files={
            "file": (
                "broken.png",
                b"\x89PNG\r\n\x1a\nnot-a-real-image",
                "image/png",
            )
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert called is False
    assert list(receipt_service.storage.root.rglob("*")) == []
    assert client.get("/receipts", headers=headers).json() == []


def test_webp_is_rejected_before_ocr_and_persistence(client, monkeypatch):
    headers = auth_headers(client)
    called = False

    async def unexpected_ocr(*_args):
        nonlocal called
        called = True
        return successful_result()

    monkeypatch.setattr(ocr_client, "extract_receipt", unexpected_ocr)
    response = client.post(
        "/receipts",
        headers=headers,
        files={"file": ("receipt.webp", WEBP_BYTES, "image/webp")},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert called is False
    assert list(receipt_service.storage.root.rglob("*")) == []
    assert client.get("/receipts", headers=headers).json() == []


def test_size_limit_and_missing_file_are_400(client, monkeypatch):
    headers = auth_headers(client)
    monkeypatch.setattr(config.settings, "MAX_UPLOAD_SIZE_BYTES", 16)

    too_large = client.post(
        "/receipts",
        headers=headers,
        files={"file": ("receipt.png", PNG_BYTES, "image/png")},
    )
    assert too_large.status_code == 400
    assert too_large.json()["error"]["code"] == "VALIDATION_ERROR"

    missing = client.post("/receipts", headers=headers)
    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "VALIDATION_ERROR"


def test_content_type_mismatch_is_400(client):
    headers = auth_headers(client)
    response = client.post(
        "/receipts",
        headers=headers,
        files={"file": ("receipt.png", PNG_BYTES, "image/jpeg")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_receipts_require_authentication(client):
    response = client.get("/receipts")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_receipts_are_isolated_by_owner(client, monkeypatch):
    headers_a = auth_headers(client, "a@example.com")
    headers_b = auth_headers(client, "b@example.com")

    async def fake_extract(*_args):
        return successful_result(vendor="A 상점")

    monkeypatch.setattr(ocr_client, "extract_receipt", fake_extract)
    created = client.post(
        "/receipts",
        headers=headers_a,
        files={"file": ("receipt.png", PNG_BYTES, "image/png")},
    )
    receipt_id = created.json()["id"]

    own_list = client.get("/receipts", headers=headers_a)
    other_list = client.get("/receipts", headers=headers_b)
    assert [item["id"] for item in own_list.json()] == [receipt_id]
    assert other_list.json() == []

    other_detail = client.get(f"/receipts/{receipt_id}", headers=headers_b)
    assert other_detail.status_code == 404
    assert other_detail.json()["error"]["code"] == "NOT_FOUND"


def test_missing_receipt_detail_is_404(client):
    headers = auth_headers(client)
    response = client.get("/receipts/999999", headers=headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_receipt_list_is_newest_first(client, monkeypatch):
    headers = auth_headers(client)

    async def fake_extract(*_args):
        return successful_result()

    monkeypatch.setattr(ocr_client, "extract_receipt", fake_extract)
    first = client.post(
        "/receipts",
        headers=headers,
        files={"file": ("first.png", PNG_BYTES, "image/png")},
    )
    time.sleep(0.01)
    second = client.post(
        "/receipts",
        headers=headers,
        files={"file": ("second.png", PNG_BYTES, "image/png")},
    )
    listing = client.get("/receipts", headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert listing.status_code == 200
    assert listing.json()[0]["id"] == second.json()["id"]


def test_parser_normalizes_vendor_amount_and_transaction_date():
    payload = {
        "version": "V2",
        "images": [
            {
                "inferResult": "SUCCESS",
                "fields": [
                    {"name": "상호명", "inferText": "  테스트 상점  "},
                    {"name": "총금액", "inferText": "4,500원"},
                    {"name": "작성일자", "inferText": "2026. 09. 15."},
                ],
            }
        ],
    }
    parsed = ocr_client.parse_response(payload)
    assert parsed is not None
    assert parsed.vendor == "테스트 상점"
    assert parsed.amount == 4500.0
    assert parsed.date == date(2026, 9, 15)
    assert parsed.ocr_raw == "테스트 상점\n4,500원\n2026. 09. 15."


def test_supply_value_alone_is_not_treated_as_total():
    payload = {
        "images": [
            {
                "inferResult": "SUCCESS",
                "fields": [
                    {"name": "상호명", "inferText": "테스트 상점"},
                    {"name": "공급가액", "inferText": "4,000원"},
                    {"name": "작성일자", "inferText": "2026-09-15"},
                ],
            }
        ],
    }
    assert ocr_client.parse_response(payload) is None


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class TimeoutClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, *_args, **_kwargs):
        raise httpx.ReadTimeout("OCR timed out")


class MalformedClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, *_args, **_kwargs):
        return FakeResponse(200, {"images": [{"inferResult": "SUCCESS"}]})


class StatusClient:
    def __init__(self, status_code):
        self.status_code = status_code

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, *_args, **_kwargs):
        return FakeResponse(self.status_code, {"message": "upstream failure"})


class CapturingClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, url, headers, data, files):
        assert url == "https://ocr.example.test/custom"
        assert headers == {"X-OCR-SECRET": "secret"}
        message = json.loads(data["message"])
        assert message["version"] == "V2"
        assert message["lang"] == "ko"
        assert message["images"][0]["format"] == "png"
        assert files["file"][0] == "receipt.png"
        return FakeResponse(
            200,
            {
                "images": [
                    {
                        "inferResult": "SUCCESS",
                        "fields": [
                            {"name": "상호명", "inferText": "테스트 상점"},
                            {"name": "총금액", "inferText": "4,500"},
                            {"name": "작성일자", "inferText": "2026-09-15"},
                        ],
                    }
                ]
            },
        )


def test_ocr_timeout_and_malformed_response_become_failed_result(monkeypatch):
    monkeypatch.setattr(config.settings, "CLOVA_OCR_API_URL", "https://ocr.example.test/custom")
    monkeypatch.setattr(config.settings, "CLOVA_OCR_SECRET_KEY", "secret")

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: TimeoutClient())
    timeout_result = asyncio.run(
        ocr_client.extract_receipt(PNG_BYTES, "image/png")
    )
    assert timeout_result is None

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: MalformedClient())
    malformed_result = asyncio.run(
        ocr_client.extract_receipt(PNG_BYTES, "image/png")
    )
    assert malformed_result is None

    class BadJsonClient(MalformedClient):
        async def post(self, *_args, **_kwargs):
            return FakeResponse(
                200,
                json.JSONDecodeError("invalid JSON", "{", 1),
            )

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: BadJsonClient())
    bad_json_result = asyncio.run(
        ocr_client.extract_receipt(PNG_BYTES, "image/png")
    )
    assert bad_json_result is None


@pytest.mark.parametrize("status_code", [401, 429, 500])
def test_ocr_http_failures_become_failed_result(monkeypatch, status_code):
    monkeypatch.setattr(config.settings, "CLOVA_OCR_API_URL", "https://ocr.example.test/custom")
    monkeypatch.setattr(config.settings, "CLOVA_OCR_SECRET_KEY", "secret")
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **_kwargs: StatusClient(status_code),
    )

    result = asyncio.run(ocr_client.extract_receipt(PNG_BYTES, "image/png"))
    assert result is None


def test_ocr_request_uses_custom_v2_multipart_contract(monkeypatch):
    monkeypatch.setattr(config.settings, "CLOVA_OCR_API_URL", "https://ocr.example.test/custom")
    monkeypatch.setattr(config.settings, "CLOVA_OCR_SECRET_KEY", "secret")
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: CapturingClient())

    result = asyncio.run(ocr_client.extract_receipt(PNG_BYTES, "image/png"))
    assert result is not None
    assert result.vendor == "테스트 상점"
    assert result.amount == 4500.0
    assert result.date == date(2026, 9, 15)
    assert result.ocr_raw == "테스트 상점\n4,500\n2026-09-15"


def test_non_template_ocr_shapes_do_not_succeed():
    general = {
        "images": [
            {
                "inferResult": "SUCCESS",
                "fields": [
                    {"inferText": "테스트 상점", "lineBreak": True},
                    {"inferText": "합계", "lineBreak": False},
                    {"inferText": "4,500", "lineBreak": True},
                    {"inferText": "2026-09-15", "lineBreak": True},
                ],
            }
        ]
    }
    document = {
        "images": [
            {
                "inferResult": "SUCCESS",
                "receipt": {
                    "result": {
                        "storeInfo": {"name": {"text": "테스트 상점"}},
                        "paymentInfo": {"date": {"text": "2026-09-15"}},
                        "totalPrice": {"price": {"text": "4,500"}},
                    }
                },
            }
        ]
    }

    assert ocr_client.parse_response(general) is None
    assert ocr_client.parse_response(document) is None


def test_storage_failure_is_distinct_from_ocr_failure(client, monkeypatch):
    headers = auth_headers(client)

    def fail_save(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(receipt_service.storage, "save", fail_save)
    response = client.post(
        "/receipts",
        headers=headers,
        files={"file": ("receipt.png", PNG_BYTES, "image/png")},
    )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "STORAGE_ERROR"


def test_database_failure_cleans_file_and_is_distinct(tmp_path, monkeypatch):
    from sqlmodel import SQLModel, Session, create_engine, select

    from app.auth.models import User
    from app.receipts.models import Receipt

    engine = create_engine(
        f"sqlite:///{tmp_path / 'pre-commit.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    storage = receipt_service.LocalFileStorage(tmp_path / "storage")
    monkeypatch.setattr(receipt_service, "storage", storage)

    async def fake_extract(*_args):
        return successful_result()

    monkeypatch.setattr(ocr_client, "extract_receipt", fake_extract)

    with Session(engine) as session:
        user = User(email="precommit@example.com", password_hash="hash", name="PreCommit")
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id

    class PreCommitFailingSession(Session):
        def flush(self):
            raise RuntimeError("database unavailable before commit")

    with PreCommitFailingSession(engine) as session:
        with pytest.raises(AppException) as error:
            asyncio.run(
                receipt_service.upload_receipt(
                    session, user_id, PNG_BYTES, "image/png"
                )
            )
    assert error.value.status_code == 500
    assert error.value.code == "DATABASE_ERROR"
    assert not list(storage.root.rglob("*.png"))
    with Session(engine) as session:
        assert session.exec(select(Receipt).where(Receipt.user_id == user_id)).first() is None


def test_refresh_failure_after_commit_keeps_row_and_file(tmp_path, monkeypatch):
    from sqlmodel import SQLModel, Session, create_engine, select

    from app.auth.models import User
    from app.receipts.models import Receipt
    from sqlalchemy.exc import OperationalError

    engine = create_engine(
        f"sqlite:///{tmp_path / 'post-commit.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    storage = receipt_service.LocalFileStorage(tmp_path / "storage")
    monkeypatch.setattr(receipt_service, "storage", storage)

    async def fake_extract(*_args):
        return successful_result()

    monkeypatch.setattr(ocr_client, "extract_receipt", fake_extract)

    with Session(engine) as session:
        user = User(email="refresh@example.com", password_hash="hash", name="Refresh")
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id

    class RefreshFailSession(Session):
        def refresh(self, *args, **kwargs):
            raise OperationalError(
                "SELECT", {}, Exception("simulated post-commit refresh failure")
            )

    with RefreshFailSession(engine) as session:
        with pytest.raises(AppException) as error:
            asyncio.run(
                receipt_service.upload_receipt(
                    session, user_id, PNG_BYTES, "image/png"
                )
            )

    assert error.value.code == "DATABASE_ERROR"
    with Session(engine) as session:
        persisted = session.exec(
            select(Receipt).where(Receipt.user_id == user_id)
        ).one()
        assert persisted.status == "done"
        assert (storage.root / persisted.image_url).is_file()


def test_uncertain_commit_failure_keeps_row_and_file(tmp_path, monkeypatch):
    from sqlmodel import SQLModel, Session, create_engine, select

    from app.auth.models import User
    from app.receipts.models import Receipt
    from sqlalchemy.exc import OperationalError

    engine = create_engine(
        f"sqlite:///{tmp_path / 'uncertain-commit.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    storage = receipt_service.LocalFileStorage(tmp_path / "storage")
    monkeypatch.setattr(receipt_service, "storage", storage)

    async def fake_extract(*_args):
        return successful_result()

    monkeypatch.setattr(ocr_client, "extract_receipt", fake_extract)

    with Session(engine) as session:
        user = User(email="unknown@example.com", password_hash="hash", name="Unknown")
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id

    class CommitUnknownSession(Session):
        def commit(self):
            super().commit()
            raise OperationalError("COMMIT", {}, Exception("connection lost after commit"))

    with CommitUnknownSession(engine) as session:
        with pytest.raises(AppException) as error:
            asyncio.run(
                receipt_service.upload_receipt(
                    session, user_id, PNG_BYTES, "image/png"
                )
            )

    assert error.value.code == "DATABASE_ERROR"
    with Session(engine) as session:
        persisted = session.exec(
            select(Receipt).where(Receipt.user_id == user_id)
        ).one()
        assert (storage.root / persisted.image_url).is_file()


def test_unexpected_ocr_error_is_not_hidden_as_failed(client, monkeypatch):
    headers = auth_headers(client)

    async def raise_unexpected(*_args):
        raise RuntimeError("unexpected parser bug")

    monkeypatch.setattr(ocr_client, "extract_receipt", raise_unexpected)
    with pytest.raises(RuntimeError):
        client.post(
            "/receipts",
            headers=headers,
            files={"file": ("receipt.png", PNG_BYTES, "image/png")},
        )

    assert client.get("/receipts", headers=headers).json() == []
