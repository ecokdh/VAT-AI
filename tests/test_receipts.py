import asyncio
from datetime import date
from io import BytesIO
import json
import time

import httpx
import pytest
from PIL import Image

from app.auth import service as auth_service
from app.business.schemas import BusinessVerifyResponse
from app.core import config
from app.receipts.ocr import ocr_client
from app.receipts import service as receipt_service


def image_bytes(format_name: str) -> bytes:
    """작은 정상 이미지 합성 fixture. 외부 영수증 원본은 사용하지 않는다."""
    output = BytesIO()
    Image.new("RGB", (4, 4), color=(255, 255, 255)).save(output, format=format_name)
    return output.getvalue()


PNG_BYTES = image_bytes("PNG")
JPEG_BYTES = image_bytes("JPEG")
WEBP_BYTES = image_bytes("WEBP")


@pytest.fixture(autouse=True)
def mock_business_verification(monkeypatch):
    monkeypatch.setattr(auth_service, "verify_business", lambda _: BusinessVerifyResponse(
        business_number="1234567890", business_status="계속사업자",
        business_status_code="01", tax_type="부가가치세 일반과세자",
        tax_type_code="01", verified=True,
    ))


def auth_headers(client, email="owner@example.com"):
    response = client.post(
        "/auth/register",
        json={"email": email, "password": "correct-password", "name": email,
              "business_name": "Test Store", "business_number": "123-45-67890",
              "tax_profile": {"business_start_date": "2025-01-01"}, "terms_accepted": True, "privacy_accepted": True, "marketing_accepted": False},
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def upload(client, headers, filename="receipt.png", content=PNG_BYTES, content_type="image/png"):
    return client.post("/v2/receipt-jobs", headers=headers, files={"file": (filename, content, content_type)})


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
    response = upload(client, auth_headers(client), filename, content, content_type)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    ("filename", "content", "content_type"),
    [
        ("broken.png", b"\x89PNG\r\n\x1a\nnot-a-real-image", "image/png"),
        ("receipt.webp", WEBP_BYTES, "image/webp"),
    ],
)
def test_rejected_image_creates_no_file_or_receipt(client, filename, content, content_type):
    headers = auth_headers(client)
    response = upload(client, headers, filename, content, content_type)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert list(receipt_service.storage.root.rglob("*")) == []
    assert client.get("/receipts", headers=headers).json() == []


def test_size_limit_and_missing_file_are_400(client, monkeypatch):
    headers = auth_headers(client)
    monkeypatch.setattr(config.settings, "MAX_UPLOAD_SIZE_BYTES", 16)

    too_large = upload(client, headers)
    assert too_large.status_code == 400
    assert too_large.json()["error"]["code"] == "VALIDATION_ERROR"

    missing = client.post("/v2/receipt-jobs", headers=headers)
    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "VALIDATION_ERROR"


def test_content_type_mismatch_is_400(client):
    response = upload(client, auth_headers(client), content_type="image/jpeg")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_receipts_require_authentication(client):
    response = client.get("/receipts")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_receipts_are_isolated_by_owner(client):
    headers_a = auth_headers(client, "a@example.com")
    headers_b = auth_headers(client, "b@example.com")
    receipt_id = upload(client, headers_a).json()["receipt_id"]

    own_list = client.get("/receipts", headers=headers_a)
    other_list = client.get("/receipts", headers=headers_b)
    assert [item["id"] for item in own_list.json()] == [receipt_id]
    assert "image_url" not in own_list.json()[0]
    assert other_list.json() == []

    assert client.get(f"/receipts/{receipt_id}", headers=headers_a).status_code == 200
    other_detail = client.get(f"/receipts/{receipt_id}", headers=headers_b)
    assert other_detail.status_code == 404
    assert other_detail.json()["error"]["code"] == "NOT_FOUND"


def test_missing_receipt_detail_is_404(client):
    headers = auth_headers(client)
    response = client.get("/receipts/999999", headers=headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_receipt_list_is_newest_first(client):
    headers = auth_headers(client)
    first = upload(client, headers, "first.png")
    time.sleep(0.01)
    second = upload(client, headers, "second.jpg", JPEG_BYTES, "image/jpeg")
    listing = client.get("/receipts", headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert listing.status_code == 200
    assert listing.json()[0]["id"] == second.json()["receipt_id"]


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


def test_general_and_document_ocr_shapes_succeed():
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

    res_general = ocr_client.parse_response(general)
    assert res_general is not None
    assert res_general.vendor == "테스트 상점"
    assert res_general.amount == 4500.0
    assert res_general.date == date(2026, 9, 15)

    res_document = ocr_client.parse_response(document)
    assert res_document is not None
    assert res_document.vendor == "테스트 상점"
    assert res_document.amount == 4500.0
    assert res_document.date == date(2026, 9, 15)


def test_storage_failure_is_distinct_from_ocr_failure(client, monkeypatch):
    headers = auth_headers(client)

    def fail_save(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(receipt_service.storage, "save", fail_save)
    response = upload(client, headers)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "STORAGE_ERROR"
