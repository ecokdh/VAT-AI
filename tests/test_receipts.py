import asyncio
from datetime import date
from io import BytesIO
import json
import time

import httpx
import pytest
from PIL import Image, ImageDraw

from app.common.exceptions import AppException
from app.auth import service as auth_service
from app.business.schemas import BusinessVerifyResponse
from app.core import config
from app.receipts import ocr_client
from app.receipts import service as receipt_service


def tiny_image_bytes(format_name: str) -> bytes:
    """OCR fallback이 건너뛸 정도로 작은 이미지."""
    output = BytesIO()
    Image.new("RGB", (4, 4), color=(255, 255, 255)).save(output, format=format_name)
    return output.getvalue()


def receipt_like_bytes(format_name: str, color=(245, 245, 245)) -> bytes:
    """품질 확인을 통과하는 합성 영수증. 외부 원본은 쓰지 않는다."""
    image = Image.new("RGB", (320, 240), color)
    draw = ImageDraw.Draw(image)
    line = (30, 30, 30) if color[0] > 80 else (200, 200, 200)
    draw.rectangle([24, 20, 296, 220], outline=line, width=3)
    for i in range(8):
        y = 48 + i * 18
        draw.line([(40, y), (280, y)], fill=line, width=2)
    output = BytesIO()
    image.save(output, format=format_name)
    return output.getvalue()


TINY_PNG = tiny_image_bytes("PNG")
PNG_BYTES = receipt_like_bytes("PNG")
JPEG_BYTES = receipt_like_bytes("JPEG")
WEBP_BYTES = tiny_image_bytes("WEBP")
DARK_PNG = receipt_like_bytes("PNG", color=(12, 12, 12))


def with_revision(client, path, headers, payload):
    """These regressions edit the currently fetched receipt; stale tests pass old snapshots explicitly."""
    receipt_path = path.split("/ocr", 1)[0]
    current = client.get(receipt_path, headers=headers)
    return {"base_revision": current.json().get("revision", 1), **payload}


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
              "business_name": "Test Store", "business_number": "123-45-67890"},
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


@pytest.mark.parametrize("inputs, expected", [
    ({"transaction_amount": 18780, "tax_exempt_amount": 12800, "vat_amount": 543}, {"taxable_supply_amount": 5437}),
    ({"transaction_amount": 6940, "tax_exempt_amount": 6940}, {"taxable_supply_amount": 0, "vat_amount": 0}),
    ({"transaction_amount": 11000, "tax_exempt_amount": 0, "vat_amount": 1000}, {"taxable_supply_amount": 10000}),
    ({"taxable_supply_amount": 10000, "tax_exempt_amount": 5000, "vat_amount": 1000}, {"transaction_amount": 16000}),
    ({"transaction_amount": 16000, "taxable_supply_amount": 10000, "vat_amount": 1000}, {"tax_exempt_amount": 5000}),
    ({"transaction_amount": 16000, "taxable_supply_amount": 10000, "tax_exempt_amount": 5000}, {"vat_amount": 1000}),
    ({"transaction_amount": 10000}, {}),
    ({"payment_amount": 16400}, {}),
    ({"transaction_amount": 5000, "tax_exempt_amount": 6000, "vat_amount": 0}, {}),
])
def test_money_only_completes_determined_missing_values(inputs, expected):
    from app.receipts.money import complete_money

    sources = {field: {"kind": "printed"} for field in inputs}
    values, result_sources = complete_money(inputs, sources)
    assert {field: value for field, value in values.items() if field not in inputs} == expected
    assert all(values[field] == value for field, value in inputs.items())
    assert all(result_sources[field]["kind"] == "calculated" for field in expected)
    assert inputs == {field: values[field] for field in inputs}


def test_legacy_supply_is_not_reinterpreted_as_taxable_supply():
    from app.receipts.money import complete_money, money_problem

    legacy = {"amount": 18780, "supply_amount": 18237, "vat_amount": 543}
    result, _ = complete_money(legacy, {})
    assert result == legacy
    assert money_problem(result, required=True) is not None


def test_ocr_separates_printed_taxable_exempt_total_and_payment():
    payload = {"images": [{"fields": [
        {"name": "상호", "inferText": "혼합 상점"},
        {"name": "거래일", "inferText": "2026-10-05"},
        {"name": "총액", "inferText": "18,780"},
        {"name": "면세금액", "inferText": "12,800"},
        {"name": "부가세", "inferText": "543"},
        {"name": "결제금액", "inferText": "17,780"},
    ]}]}
    result = ocr_client.parse_response(payload)
    assert result.transaction_amount == 18780
    assert result.payment_amount == 17780
    assert result.tax_exempt_amount == 12800
    assert result.taxable_supply_amount is None  # 계산은 저장 단계에서 별도 표시한다.


@pytest.mark.parametrize("quantity, amount, expected", [(2, 3333, 1666.5), (3, 100, 100 / 3), (5, 0, 0)])
def test_missing_unit_price_uses_line_amount_and_quantity(quantity, amount, expected):
    from app.receipts.money import complete_unit_price, unit_price_problem

    original = {"quantity": quantity, "line_amount": amount, "unit_price": None}
    row = complete_unit_price(original)
    assert row["unit_price"] == pytest.approx(expected)
    assert row["sources"]["unit_price"]["kind"] == "calculated"
    assert original["unit_price"] is None
    assert unit_price_problem([row]) is None
    printed = complete_unit_price({**original, "unit_price": 2000, "sources": {"unit_price": {"kind": "printed"}}})
    assert printed["unit_price"] == 2000  # 인쇄 단가와 할인 후 행 금액이 달라도 덮지 않는다.
    assert printed["sources"]["unit_price"]["kind"] == "printed"


def test_order_subtotal_is_not_discounted_transaction_total():
    fields = [{"name": "상호", "inferText": "주문 상점"},
        {"name": "거래일", "inferText": "2026-10-05"},
        {"inferText": "배달 주문서"}, {"name": "총액", "inferText": "23400"},
        {"name": "결제금액", "inferText": "16400"}]
    result = ocr_client.parse_response({"images": [{"fields": fields}]})
    assert result.subtotal_amount == 23400
    assert result.payment_amount == 16400
    assert result.transaction_amount is None
    fields.append({"name": "할인후합계", "inferText": "16400"})
    result = ocr_client.parse_response({"images": [{"fields": fields}]})
    assert result.transaction_amount == 16400
    assert result.subtotal_amount == 23400


def test_unit_price_save_recompute_override_staleness_and_name_binding(client, monkeypatch):
    headers = auth_headers(client)

    async def fake_extract(*_args):
        return ocr_client.OcrResult(vendor="단가 검증", amount=6940, date=date(2026, 10, 5),
            ocr_raw="단가 검증", items=("생수",), transaction_amount=6940, tax_exempt_amount=6940)

    monkeypatch.setattr(ocr_client, "extract_receipt", fake_extract)
    created = client.post("/receipts", headers=headers, files={"file": ("receipt.png", PNG_BYTES, "image/png")}).json()
    path = f"/receipts/{created['id']}"
    for invalid in (0, -1, True, "2"):
        assert client.patch(path + "/ocr", headers=headers, json=with_revision(client, path + "/ocr", headers, {"item_amounts": [{"item_index": 0, "quantity": invalid, "line_amount": 6000}]})).status_code == 400
    assert client.patch(path + "/ocr", headers=headers, json=with_revision(client, path + "/ocr", headers, {"item_amounts": [{"item_index": 1, "quantity": 2, "line_amount": 6000}]})).status_code == 400
    saved = client.patch(path + "/ocr", headers=headers, json=with_revision(client, path + "/ocr", headers, {"item_amounts": [{"item_index": 0, "quantity": 2, "line_amount": 6000}]})).json()
    row = saved["item_amounts"][0]
    assert row["unit_price"] == 3000
    assert row["item_name"] == "생수"
    assert row["sources"]["unit_price"]["kind"] == "calculated"
    updated = client.patch(path + "/ocr", headers=headers, json=with_revision(client, path + "/ocr", headers, {"item_amounts": [{"item_index": 0, "quantity": 3, "line_amount": 6000, "unit_price": 3000}], "base_item_amounts": saved["item_amounts"]})).json()
    assert updated["item_amounts"][0]["unit_price"] == 2000
    assert client.patch(path + "/ocr", headers=headers, json=with_revision(client, path + "/ocr", headers, {"item_amounts": [], "base_item_amounts": saved["item_amounts"]})).status_code == 409
    overridden = client.patch(path + "/ocr", headers=headers, json=with_revision(client, path + "/ocr", headers, {"item_amounts": [{"item_index": 0, "quantity": 3, "line_amount": 6000, "unit_price": 2500}]})).json()
    assert overridden["item_amounts"][0]["unit_price"] == 2500
    assert overridden["item_amounts"][0]["sources"]["unit_price"]["kind"] == "manual"
    missing = client.patch(path + "/ocr", headers=headers, json=with_revision(client, path + "/ocr", headers, {"item_amounts": [{"item_index": 0, "quantity": 3}]})).json()
    assert missing["item_amounts"][0]["unit_price"] is None
    assert missing["line_items"][0]["effective_unit_price"] is None
    renamed = client.patch(path + "/ocr", headers=headers, json=with_revision(client, path + "/ocr", headers, {"items": ["다른 상품"]})).json()
    assert renamed["item_amounts"] == []
    assert client.post(path + "/ocr/confirm", headers=headers, json=with_revision(client, path + "/ocr/confirm", headers, {"confirmed": True})).status_code == 200


def test_new_receipt_cannot_bypass_breakdown_by_clearing_new_fields(client, monkeypatch):
    headers = auth_headers(client)

    async def fake_extract(*_args):
        return successful_result()

    monkeypatch.setattr(ocr_client, "extract_receipt", fake_extract)
    created = client.post("/receipts", headers=headers, files={"file": ("receipt.png", PNG_BYTES, "image/png")}).json()
    assert created["money_schema_version"] == 2
    path = f"/receipts/{created['id']}"
    cleared = client.patch(path + "/ocr", headers=headers, json=with_revision(client, path + "/ocr", headers, {"taxable_supply_amount": None, "tax_exempt_amount": None, "transaction_amount": None, "payment_amount": None})).json()
    assert cleared["money_schema_version"] == 2
    assert client.post(path + "/ocr/confirm", headers=headers, json=with_revision(client, path + "/ocr/confirm", headers, {"confirmed": True})).status_code == 409


def test_subtotal_and_payment_do_not_fill_missing_tax_breakdown(client, monkeypatch):
    headers = auth_headers(client)

    async def fake_extract(*_args):
        return successful_result()

    monkeypatch.setattr(ocr_client, "extract_receipt", fake_extract)
    created = client.post("/receipts", headers=headers, files={"file": ("receipt.png", PNG_BYTES, "image/png")}).json()
    path = f"/receipts/{created['id']}"
    saved = client.patch(path + "/ocr", headers=headers, json=with_revision(client, path + "/ocr", headers, {"subtotal_amount": 23400, "payment_amount": 16400})).json()
    assert saved["transaction_amount"] is None
    assert saved["taxable_supply_amount"] is None
    assert saved["vat_amount"] is None
    assert client.post(path + "/ocr/confirm", headers=headers, json=with_revision(client, path + "/ocr/confirm", headers, {"confirmed": True})).status_code == 409
    assert client.patch(path + "/ocr", headers=headers, json=with_revision(client, path + "/ocr", headers, {"subtotal_amount": 25000})).status_code == 200
    assert client.patch(path + "/ocr", headers=headers, json=with_revision(client, path + "/ocr", headers, {"subtotal_amount": 23400, "base_subtotal_amount": 23400})).status_code == 409


@pytest.mark.parametrize("change", ["item_amounts", "schema_version"])
def test_confirmation_guards_item_numbers_and_schema_version(tmp_path, change):
    from sqlmodel import Session, SQLModel, create_engine
    from app.auth.models import User
    from app.receipts.models import Receipt
    from app.receipts.schemas import ReceiptConfirmIn, ReceiptOcrUpdate
    from app.receipts.money import complete_unit_price

    engine = create_engine(f"sqlite:///{tmp_path / 'amount-details-race.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as seed:
        user = User(email="details-race@example.com", password_hash="x", name="검증")
        seed.add(user)
        seed.commit()
        row = Receipt(user_id=user.id, image_url="test.png", vendor="상점", amount=11000,
            supply_amount=10000, vat_amount=1000, date=date(2026, 10, 5), status="done",
            taxable_supply_amount=10000, tax_exempt_amount=0, transaction_amount=11000,
            items_json=json.dumps(["생수"]), item_amounts_json=json.dumps([
                complete_unit_price({"item_index": 0, "item_name": "생수", "quantity": 2, "line_amount": 6000})
            ]))
        seed.add(row)
        seed.commit()
        receipt_id, user_id = row.id, user.id
    with Session(engine) as confirmer:
        previous = confirmer.get(Receipt, receipt_id)
        assert previous.money_schema_version == 1
        with Session(engine) as editor:
            payload = ReceiptOcrUpdate(base_revision=1, item_amounts=[{"item_index": 0, "quantity": 3, "line_amount": 6000}]) if change == "item_amounts" else ReceiptOcrUpdate(base_revision=1, transaction_amount=None)
            receipt_service.update_ocr(editor, user_id, receipt_id, payload)
        with pytest.raises(AppException) as caught:
            receipt_service.confirm_receipt(confirmer, user_id, receipt_id, ReceiptConfirmIn(base_revision=1))
        assert caught.value.status_code == 409
        assert "바뀌었" in caught.value.message
    with Session(engine) as checker:
        assert checker.get(Receipt, receipt_id).confirmed is False


def test_mixed_money_save_recomputes_derived_values_and_preserves_original(client, monkeypatch):
    headers = auth_headers(client)

    async def fake_extract(*_args):
        return ocr_client.OcrResult(vendor="혼합 상점", amount=18780, date=date(2026, 10, 5),
            ocr_raw="혼합 상점", transaction_amount=18780, tax_exempt_amount=12800, vat_amount=543)

    monkeypatch.setattr(ocr_client, "extract_receipt", fake_extract)
    created = client.post("/receipts", headers=headers, files={"file": ("receipt.png", PNG_BYTES, "image/png")}).json()
    assert created["taxable_supply_amount"] == 5437
    assert created["money_sources"]["taxable_supply_amount"]["kind"] == "calculated"
    original = created["ocr_original"]
    assert json.loads(original)["taxable_supply_amount"] is None
    path = f"/receipts/{created['id']}"
    saved = client.patch(path + "/ocr", headers=headers, json=with_revision(client, path + "/ocr", headers, {
        "transaction_amount": 20000, "tax_exempt_amount": 12800, "vat_amount": 543,
        "taxable_supply_amount": 5437, "payment_amount": 19000,
        "base_transaction_amount": 18780, "base_taxable_supply_amount": 5437,
        "base_tax_exempt_amount": 12800, "base_payment_amount": None,
    }))
    assert saved.status_code == 200
    body = saved.json()
    assert body["taxable_supply_amount"] == 6657
    assert body["money_sources"]["taxable_supply_amount"]["kind"] == "calculated"
    assert body["money_sources"]["transaction_amount"]["kind"] == "manual"
    assert body["payment_amount"] == 19000  # 결제 금액은 거래 총액과 다를 수 있다.
    assert body["amount"] == 18780  # 기존 필드를 덮거나 재해석하지 않는다.
    assert body["ocr_original"] == original
    stale = client.patch(path + "/ocr", headers=headers, json=with_revision(client, path + "/ocr", headers, {"payment_amount": 18000, "base_payment_amount": None}))
    assert stale.status_code == 409
    confirmed = client.post(path + "/ocr/confirm", headers=headers, json=with_revision(client, path + "/ocr/confirm", headers, {"confirmed": True}))
    assert confirmed.status_code == 200
    assert client.get("/receipts", headers=headers).json()[0]["transaction_amount"] == 20000


def test_unknown_tax_breakdown_and_conflicting_printed_values_cannot_confirm(client, monkeypatch):
    headers = auth_headers(client)

    async def fake_extract(*_args):
        return successful_result()

    monkeypatch.setattr(ocr_client, "extract_receipt", fake_extract)
    created = client.post("/receipts", headers=headers, files={"file": ("receipt.png", PNG_BYTES, "image/png")}).json()
    path = f"/receipts/{created['id']}"
    for payload in (
        {"transaction_amount": 10000},
        {"transaction_amount": 18780, "taxable_supply_amount": 5438, "tax_exempt_amount": 12800, "vat_amount": 543},
        {"transaction_amount": 18780, "taxable_supply_amount": 6000, "tax_exempt_amount": 12800, "vat_amount": 543},
    ):
        assert client.patch(path + "/ocr", headers=headers, json=with_revision(client, path + "/ocr", headers, payload)).status_code == 200
        assert client.post(path + "/ocr/confirm", headers=headers, json=with_revision(client, path + "/ocr/confirm", headers, {"confirmed": True})).status_code == 409
    assert client.get(path, headers=headers).json()["taxable_supply_amount"] == 6000


def test_new_financial_fields_reject_invalid_money(client, monkeypatch):
    headers = auth_headers(client)

    async def fake_extract(*_args):
        return successful_result()

    monkeypatch.setattr(ocr_client, "extract_receipt", fake_extract)
    created = client.post("/receipts", headers=headers, files={"file": ("receipt.png", PNG_BYTES, "image/png")}).json()
    for field in ("taxable_supply_amount", "tax_exempt_amount", "transaction_amount", "payment_amount", "subtotal_amount"):
        response = client.patch(f"/receipts/{created['id']}/ocr", headers=headers, json=with_revision(client, f"/receipts/{created['id']}/ocr", headers, {field: -1}))
        assert response.status_code == 400


@pytest.mark.parametrize("field, changed", [
    ("taxable_supply_amount", 11000), ("tax_exempt_amount", 1000),
    ("vat_amount", 900), ("transaction_amount", 12000), ("payment_amount", 10500),
])
def test_confirm_rejects_stale_new_money_snapshot(tmp_path, field, changed):
    from sqlmodel import Session, SQLModel, create_engine
    from app.auth.models import User
    from app.receipts.models import Receipt
    from app.receipts.schemas import ReceiptConfirmIn, ReceiptOcrUpdate

    engine = create_engine(f"sqlite:///{tmp_path / 'new-money-race.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as seed:
        user = User(email="new-money@example.com", password_hash="x", name="테스터")
        seed.add(user)
        seed.commit()
        row = Receipt(user_id=user.id, image_url="receipts/test.png", vendor="상점", date=date(2026, 10, 5),
            amount=11000, status="done", taxable_supply_amount=10000, tax_exempt_amount=0,
            vat_amount=1000, transaction_amount=11000, payment_amount=11000)
        seed.add(row)
        seed.commit()
        receipt_id, user_id = row.id, user.id
    with Session(engine) as confirmer:
        stale = confirmer.get(Receipt, receipt_id)  # 별도 연결이 저장하기 전의 검토 값
        assert stale.confirmed is False
        with Session(engine) as editor:
            receipt_service.update_ocr(editor, user_id, receipt_id, ReceiptOcrUpdate(base_revision=1, **{field: changed}))
        with pytest.raises(AppException) as caught:
            receipt_service.confirm_receipt(confirmer, user_id, receipt_id, ReceiptConfirmIn(base_revision=1))
        assert caught.value.status_code == 409
        assert "바뀌었" in caught.value.message
    with Session(engine) as checker:
        assert checker.get(Receipt, receipt_id).confirmed is False


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
        ocr_client.extract_receipt(TINY_PNG, "image/png")
    )
    assert timeout_result is None

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: MalformedClient())
    malformed_result = asyncio.run(
        ocr_client.extract_receipt(TINY_PNG, "image/png")
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
        ocr_client.extract_receipt(TINY_PNG, "image/png")
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

    result = asyncio.run(ocr_client.extract_receipt(TINY_PNG, "image/png"))
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


def test_quality_gate_skips_ocr_and_keeps_file(client, monkeypatch):
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
        files={"file": ("dark.png", DARK_PNG, "image/png")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "retake"
    assert body["quality_reason"]
    assert body["vendor"] is None
    assert body["confirmed"] is False
    assert called is False
    assert (receipt_service.storage.root / body["image_url"]).is_file()


def _box(text, x, y, w=80, h=16):
    return {
        "inferText": text,
        "boundingPoly": {
            "vertices": [
                {"x": x, "y": y},
                {"x": x + w, "y": y},
                {"x": x + w, "y": y + h},
                {"x": x, "y": y + h},
            ]
        },
    }


def test_boxes_fill_business_number_and_amounts_without_template_names():
    payload = {
        "images": [
            {
                "inferResult": "SUCCESS",
                "fields": [
                    _box("테스트 상점", 20, 10),
                    _box("123-45-67890", 20, 40),
                    _box("2026-09-15", 20, 70),
                    _box("공급가액", 20, 110),
                    _box("10,000", 120, 110),
                    _box("부가세", 20, 140),
                    _box("1,000", 120, 140),
                    _box("합계", 20, 170),
                    _box("11,000", 120, 170),
                ],
            }
        ],
    }
    parsed = ocr_client.parse_response(payload)
    assert parsed is not None
    assert parsed.vendor == "테스트 상점"
    assert parsed.business_number == "1234567890"
    assert parsed.supply_amount == 10000.0
    assert parsed.vat_amount == 1000.0
    assert parsed.amount == 11000.0
    assert parsed.date.isoformat() == "2026-09-15"
    assert parsed.text_boxes


def test_failure_response_is_not_success_and_null_receipt_does_not_crash():
    failed = {
        "images": [
            {
                "inferResult": "FAILURE",
                "fields": [
                    {"name": "상호명", "inferText": "테스트 상점"},
                    {"name": "총금액", "inferText": "11000"},
                    {"name": "작성일자", "inferText": "2026-09-15"},
                ],
            }
        ]
    }
    assert ocr_client.parse_response(failed) is None
    partial = ocr_client.collect_partial(failed)
    assert partial is not None
    assert partial.vendor == "테스트 상점"

    broken = {"images": [{"inferResult": "SUCCESS", "receipt": None}]}
    assert ocr_client.parse_response(broken) is None


def test_far_phone_number_is_not_total():
    payload = {
        "images": [
            {
                "inferResult": "SUCCESS",
                "fields": [
                    _box("테스트 상점", 20, 10),
                    _box("2026-09-15", 20, 40),
                    _box("합계", 20, 80),
                    _box("010-1234-5678", 20, 580),
                ],
            }
        ]
    }
    assert ocr_client.parse_response(payload) is None


def test_negative_amount_cannot_be_confirmed(client, monkeypatch):
    headers = auth_headers(client)

    async def fake_extract(*_args):
        return ocr_client.OcrResult(vendor="테스트 상점", amount=4500, date=date(2026, 9, 15), ocr_raw="전액 면세 검증", transaction_amount=4500, tax_exempt_amount=4500)

    monkeypatch.setattr(ocr_client, "extract_receipt", fake_extract)
    created = client.post(
        "/receipts",
        headers=headers,
        files={"file": ("receipt.png", PNG_BYTES, "image/png")},
    )
    receipt_id = created.json()["id"]
    patched = client.patch(
        f"/receipts/{receipt_id}/ocr",
        headers=headers,
        json=with_revision(client, f"/receipts/{receipt_id}/ocr", headers, {"amount": -100}),
    )
    assert patched.status_code == 400
    confirmed = client.post(
        f"/receipts/{receipt_id}/ocr/confirm",
        headers=headers,
        json=with_revision(client, f"/receipts/{receipt_id}/ocr/confirm", headers, {"confirmed": True}),
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["amount"] == 4500.0


def test_confirm_holds_the_row_until_save_so_overlap_cannot_confirm_mismatch(tmp_path):
    """확정이 금액을 읽은 뒤 저장하기 전에 다른 수정이 끼어들어도 틀린 합계는 확정되지 않는다."""
    import threading

    from sqlmodel import Session, SQLModel, create_engine

    from app.auth.models import User
    from app.receipts.models import Receipt
    from app.receipts.schemas import ReceiptConfirmIn, ReceiptOcrUpdate

    engine = create_engine(
        f"sqlite:///{tmp_path / 'race-overlap.db'}",
        connect_args={"check_same_thread": False, "timeout": 2},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(email="overlap@example.com", password_hash="x", name="테스터")
        session.add(user)
        session.commit()
        session.refresh(user)
        receipt = Receipt(
            user_id=user.id,
            image_url="receipts/overlap.png",
            vendor="테스트 상점",
            amount=11000,
            supply_amount=10000,
            taxable_supply_amount=10000,
            tax_exempt_amount=0,
            transaction_amount=11000,
            vat_amount=1000,
            date=date(2026, 9, 15),
            status="done",
            confirmed=False,
        )
        session.add(receipt)
        session.commit()
        session.refresh(receipt)
        user_id, receipt_id = user.id, receipt.id

    read_done = threading.Event()
    original_reject = receipt_service._reject_negative_money

    def stall_after_read(data, **kwargs):
        original_reject(data, **kwargs)
        if data.get("amount") == 11000 and data.get("supply_amount") == 10000:
            read_done.set()
            time.sleep(0.5)

    def edit_amount():
        assert read_done.wait(3)
        with Session(engine) as editor:
            receipt_service.update_ocr(
                editor,
                user_id,
                receipt_id,
                ReceiptOcrUpdate(base_revision=1, amount=5000, transaction_amount=5000),
            )

    worker = threading.Thread(target=edit_amount)
    worker.start()
    monkey_set = receipt_service._reject_negative_money
    receipt_service._reject_negative_money = stall_after_read
    try:
        with Session(engine) as confirmer:
            with pytest.raises(AppException) as caught:
                receipt_service.confirm_receipt(
                    confirmer,
                    user_id,
                    receipt_id,
                    ReceiptConfirmIn(base_revision=1, confirmed=True),
                )
    finally:
        receipt_service._reject_negative_money = monkey_set
        worker.join(4)

    assert caught.value.status_code == 409
    assert "바뀌었" in caught.value.message
    with Session(engine) as checker:
        row = checker.get(Receipt, receipt_id)
        assert row is not None
        assert row.confirmed is False
        assert row.amount == 5000
        assert row.supply_amount == 10000
        assert row.vat_amount == 1000


def test_stale_screen_cannot_overwrite_newer_amount(tmp_path):
    """화면이 예전 11,000원을 기억한 채 저장하면, 이미 저장된 5,000원은 되돌아가지 않는다."""
    from sqlmodel import Session, SQLModel, create_engine

    from app.auth.models import User
    from app.receipts.models import Receipt
    from app.receipts.schemas import ReceiptOcrUpdate

    engine = create_engine(
        f"sqlite:///{tmp_path / 'stale.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(email="stale@example.com", password_hash="x", name="테스터")
        session.add(user)
        session.commit()
        session.refresh(user)
        receipt = Receipt(
            user_id=user.id,
            image_url="receipts/stale.png",
            vendor="테스트 상점",
            amount=11000,
            supply_amount=10000,
            vat_amount=1000,
            date=date(2026, 9, 15),
            status="done",
            confirmed=False,
        )
        session.add(receipt)
        session.commit()
        session.refresh(receipt)
        user_id, receipt_id = user.id, receipt.id

    with Session(engine) as editor:
        receipt_service.update_ocr(
            editor,
            user_id,
            receipt_id,
            ReceiptOcrUpdate(base_revision=1, amount=5000, base_amount=11000, base_supply_amount=10000, base_vat_amount=1000),
        )

    with Session(engine) as stale:
        with pytest.raises(AppException) as caught:
            receipt_service.update_ocr(
                stale,
                user_id,
                receipt_id,
                ReceiptOcrUpdate(base_revision=1,
                    amount=11000,
                    supply_amount=10000,
                    vat_amount=1000,
                    base_amount=11000,
                    base_supply_amount=10000,
                    base_vat_amount=1000,
                ),
            )
    assert caught.value.status_code == 409
    assert "바뀌었" in caught.value.message

    with Session(engine) as checker:
        saved = checker.get(Receipt, receipt_id)
        assert saved is not None
        assert saved.confirmed is False
        assert saved.amount == 5000
        assert saved.supply_amount == 10000
        assert saved.vat_amount == 1000


def test_confirm_rejects_amount_already_saved_by_another_session(tmp_path):
    """다른 연결이 총액을 확정 전에 저장하면, 그 틀린 합계는 확정되지 않고 남는다."""
    from sqlmodel import Session, SQLModel, create_engine

    from app.auth.models import User
    from app.receipts.models import Receipt
    from app.receipts.schemas import ReceiptConfirmIn, ReceiptOcrUpdate

    engine = create_engine(
        f"sqlite:///{tmp_path / 'race.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(email="race@example.com", password_hash="x", name="테스터")
        session.add(user)
        session.commit()
        session.refresh(user)
        receipt = Receipt(
            user_id=user.id,
            image_url="receipts/race.png",
            vendor="테스트 상점",
            amount=11000,
            supply_amount=10000,
            taxable_supply_amount=10000,
            tax_exempt_amount=0,
            transaction_amount=11000,
            vat_amount=1000,
            date=date(2026, 9, 15),
            status="done",
            confirmed=False,
        )
        session.add(receipt)
        session.commit()
        session.refresh(receipt)
        user_id, receipt_id = user.id, receipt.id

    with Session(engine) as editor:
        receipt_service.update_ocr(
            editor,
            user_id,
            receipt_id,
            ReceiptOcrUpdate(base_revision=1, amount=5000, transaction_amount=5000),
        )

    with Session(engine) as confirmer:
        with pytest.raises(AppException) as caught:
            receipt_service.confirm_receipt(
                confirmer,
                user_id,
                receipt_id,
                ReceiptConfirmIn(base_revision=1, confirmed=True),
            )
    assert caught.value.status_code == 409

    with Session(engine) as checker:
        saved = checker.get(Receipt, receipt_id)
        assert saved is not None
        assert saved.confirmed is False
        assert saved.amount == 5000
        assert saved.supply_amount == 10000
        assert saved.vat_amount == 1000


def test_parser_reads_business_number_supply_vat_and_items():
    payload = {
        "images": [
            {
                "inferResult": "SUCCESS",
                "fields": [
                    {"name": "상호명", "inferText": "테스트 상점"},
                    {"name": "사업자등록번호", "inferText": "123-45-67890"},
                    {"name": "총금액", "inferText": "11,000원"},
                    {"name": "공급가액", "inferText": "10,000원"},
                    {"name": "부가세", "inferText": "1,000원"},
                    {"name": "품목", "inferText": "생수"},
                    {"name": "작성일자", "inferText": "2026-09-15"},
                ],
            }
        ],
    }
    parsed = ocr_client.parse_response(payload)
    assert parsed is not None
    assert parsed.business_number == "1234567890"
    assert parsed.supply_amount == 10000.0
    assert parsed.vat_amount == 1000.0
    assert parsed.items == ("생수",)


def test_user_can_correct_and_confirm_receipt(client, monkeypatch):
    headers = auth_headers(client)
    other = auth_headers(client, "other@example.com")

    async def fake_extract(*_args):
        return successful_result()

    monkeypatch.setattr(ocr_client, "extract_receipt", fake_extract)
    created = client.post(
        "/receipts",
        headers=headers,
        files={"file": ("receipt.png", PNG_BYTES, "image/png")},
    )
    receipt_id = created.json()["id"]
    assert created.json()["confirmed"] is False
    assert created.json()["ocr_original"]

    patched = client.patch(
        f"/receipts/{receipt_id}/ocr",
        headers=headers,
        json=with_revision(client, f"/receipts/{receipt_id}/ocr", headers, {
            "vendor": "수정 상점",
            "business_number": "1234567890",
            "taxable_supply_amount": 10000,
            "tax_exempt_amount": 0,
            "transaction_amount": 11000,
            "supply_amount": 10000,
            "vat_amount": 1000,
            "amount": 11000,
            "items": ["생수"],
        }),
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["vendor"] == "수정 상점"
    assert "테스트 상점" in body["ocr_original"]
    assert body["items"] == ["생수"]
    assert body["confirmed"] is False

    forbidden = client.patch(
        f"/receipts/{receipt_id}/ocr",
        headers=other,
        json=with_revision(client, f"/receipts/{receipt_id}/ocr", other, {"vendor": "훔친 상점"}),
    )
    assert forbidden.status_code == 404

    confirmed = client.post(
        f"/receipts/{receipt_id}/ocr/confirm",
        headers=headers,
        json=with_revision(client, f"/receipts/{receipt_id}/ocr/confirm", headers, {"confirmed": True}),
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["confirmed"] is True

    listing = client.get("/receipts/confirmed", headers=headers)
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [receipt_id]
    assert client.get("/receipts/confirmed", headers=other).json() == []


def test_confirm_blocks_retake_and_amount_mismatch(client, monkeypatch):
    headers = auth_headers(client)
    retake = client.post(
        "/receipts",
        headers=headers,
        files={"file": ("dark.png", DARK_PNG, "image/png")},
    )
    blocked = client.post(
        f"/receipts/{retake.json()['id']}/ocr/confirm",
        headers=headers,
        json=with_revision(client, f"/receipts/{retake.json()['id']}/ocr/confirm", headers, {"confirmed": True}),
    )
    assert blocked.status_code == 409

    async def fake_extract(*_args):
        return successful_result()

    monkeypatch.setattr(ocr_client, "extract_receipt", fake_extract)
    created = client.post(
        "/receipts",
        headers=headers,
        files={"file": ("receipt.png", PNG_BYTES, "image/png")},
    )
    client.patch(
        f"/receipts/{created.json()['id']}/ocr",
        headers=headers,
        json=with_revision(client, f"/receipts/{created.json()['id']}/ocr", headers, {"supply_amount": 10000, "vat_amount": 1000, "amount": 5000}),
    )
    mismatch = client.post(
        f"/receipts/{created.json()['id']}/ocr/confirm",
        headers=headers,
        json=with_revision(client, f"/receipts/{created.json()['id']}/ocr/confirm", headers, {"confirmed": True}),
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "DATA_CONFLICT"
