"""Stage 3 E2E tests for local MVP edge cases and multi-job queue processing (0 paid calls)."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

from PIL import Image
from sqlmodel import Session

from app.auth import service as auth_service
from app.business.schemas import BusinessVerifyResponse
from app.jobs import worker
from app.ocr_pipeline import luna as luna_pipeline
from app.receipts.luna_low_contract import normalize


def _make_png_bytes(color: tuple[int, int, int] = (240, 240, 240)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), color=color).save(buf, format="PNG")
    return buf.getvalue()


def _register_user(client, monkeypatch, email: str = "edge-e2e@example.com") -> dict[str, str]:
    from app.core.config import settings
    monkeypatch.setattr(settings, "OCR_PIPELINE", "app.ocr_pipeline.luna:create_pipeline")
    monkeypatch.setattr(settings, "RECEIPT_RECOGNITION_BACKEND", "luna_low")
    monkeypatch.setattr(
        auth_service,
        "verify_business",
        lambda _: BusinessVerifyResponse(
            business_number="1234567890",
            business_status="계속사업자",
            business_status_code="01",
            tax_type="부가가치세 일반과세자",
            tax_type_code="01",
            verified=True,
        ),
    )
    reg = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "correct-password",
            "name": "엣지검증",
            "business_name": "엣지상점",
            "business_number": "123-45-67890",
            "tax_profile": {"business_start_date": "2025-01-01"}, "terms_accepted": True,
            "privacy_accepted": True,
            "marketing_accepted": False,
        },
    )
    assert reg.status_code in (200, 201), reg.text
    return {"Authorization": "Bearer " + reg.json()["access_token"]}


def test_e2e_conflict_receipt_review_and_inbox_flow(client, monkeypatch):
    """Scenario A: Conflicting printed amounts trigger review warning and resolve cleanly on user confirmation."""
    from app.main import app
    from app.core.database import get_session

    headers = _register_user(client, monkeypatch, "conflict-e2e@example.com")
    img_bytes = _make_png_bytes((200, 210, 220))
    img_sha = hashlib.sha256(img_bytes).hexdigest()

    raw_conflict = {
        "h": {
            "vendor": "충돌테스트마트",
            "branch": "강남점",
            "business_number": "214-85-12345",
            "datetime": "2026-10-13 11:20:00",
        },
        "m": [
            {"role": "supply", "scope": "taxable", "label": "공급가액A", "value": 10000},
            {"role": "supply", "scope": "taxable", "label": "공급가액B", "value": 12000},
            {"role": "vat", "scope": "unknown", "label": "부가세", "value": 1000},
            {"role": "total", "scope": "unknown", "label": "합계", "value": 11000},
            {"role": "payment", "scope": "unknown", "label": "카드결제", "value": 11000},
        ],
        "i": [{"n": "테스트상품", "q": 1, "u": 11000, "p": 11000, "t": "item", "parent": None}],
        "uncertain": ["공급가액 인쇄가 겹쳐 보입니다."],
    }

    async def fake_recognize(image_bytes: bytes, mime_type: str):
        return {
            "engine": "luna_low",
            "model": "gpt-6-luna",
            "reasoning_effort": "low",
            "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
            "request_id": "req_conflict_test",
            "document": normalize(raw_conflict),
            "raw_prediction": raw_conflict,
            "confirmed": False,
        }

    monkeypatch.setattr(luna_pipeline, "recognize", fake_recognize)

    enq = client.post(
        "/v2/receipt-jobs?direction=purchase",
        headers=headers,
        files={"file": ("conflict.png", img_bytes, "image/png")},
    )
    assert enq.status_code == 202, enq.text
    receipt_id = enq.json()["receipt_id"]

    # Run worker using test DB session
    gen = app.dependency_overrides[get_session]()
    test_session: Session = next(gen)
    try:
        monkeypatch.setattr(worker, "engine", test_session.get_bind())
        assert worker.process_one() is True
    finally:
        gen.close()

    detail = client.get(f"/v2/receipts/{receipt_id}", headers=headers).json()
    assert detail["status"] == "done"
    assert detail["stage_statuses"]["missing_field_check"] == "failed"
    assert "금액 후보 충돌: supply_amount" in detail["ocr_warnings"]
    assert "공급가액 인쇄가 겹쳐 보입니다." in detail["ocr_warnings"]
    assert detail["recognition"]["document"]["fields"]["supply_amount"] is None
    assert "supply_amount" in detail["recognition"]["document"]["conflicts"]

    # User resolves conflict in ReceiptReviewEditor and confirms extraction
    confirm_payload = {
        "vendor": "충돌테스트마트",
        "amount": 11000,
        "date": "2026-10-13",
        "document": {
            "fields": {
                "vendor": "충돌테스트마트",
                "branch": "강남점",
                "business_number": "214-85-12345",
                "transaction_datetime": "2026-10-13 11:20:00",
                "printed_total_amount": 11000,
                "payment_amount": 11000,
                "supply_amount": 10000,
                "taxable_supply_amount": 10000,
                "vat_amount": 1000,
                "tax_exempt_amount": None,
                "discount_amount": None,
                "subtotal_amount": None,
            },
            "items": [
                {
                    "name": "테스트상품",
                    "quantity": 1,
                    "unit_price": 11000,
                    "line_amount": 11000,
                    "row_type": "item",
                    "parent_row": None,
                }
            ],
        },
        "purpose": "사무용품 구입",
        "evidence_type": "card_receipt",
        "business_related": True,
        "tax_treatment": "standard",
    }
    conf_resp = client.post(f"/v2/receipts/{receipt_id}/confirm-extraction", headers=headers, json=confirm_payload)
    assert conf_resp.status_code == 200, conf_resp.text

    updated = client.get(f"/v2/receipts/{receipt_id}", headers=headers).json()
    assert updated["extraction_confirmed"] is True
    assert updated["recognition"]["document"]["fields"]["supply_amount"] == 10000
    assert updated["recognition"]["document"]["conflicts"] == []
    assert "supply_amount" in updated["recognition"]["original_document"]["conflicts"]
    assert updated["review"]["field_sources"]["supply_amount"] == "user_edit"
    assert updated["review"]["field_sources"]["vat_amount"] == "user_confirmed"


def test_e2e_negative_cancellation_receipt_and_item_parent_reindex(client, monkeypatch):
    """Scenarios B & C: Negative cancellation receipt warning + middle item deletion parent_row re-indexing."""
    from app.main import app
    from app.core.database import get_session

    headers = _register_user(client, monkeypatch, "neg-e2e@example.com")
    img_bytes = _make_png_bytes((220, 200, 200))

    raw_negative = {
        "h": {
            "vendor": "취소영수증카페",
            "branch": None,
            "business_number": "101-81-99999",
            "datetime": "2026-10-13 13:00:00",
        },
        "m": [
            {"role": "supply", "scope": "taxable", "label": "공급가액", "value": -10000},
            {"role": "vat", "scope": "unknown", "label": "부가세", "value": -1000},
            {"role": "total", "scope": "unknown", "label": "합계", "value": -11000},
            {"role": "payment", "scope": "unknown", "label": "카드취소", "value": -11000},
        ],
        "i": [
            {"n": "삭제할상품", "q": 1, "u": 5000, "p": 5000, "t": "item", "parent": None},
            {"n": "유지할상품", "q": 1, "u": 6000, "p": 6000, "t": "item", "parent": None},
            {"n": "유지할상품할인", "q": None, "u": None, "p": -1000, "t": "discount", "parent": 1},
        ],
        "uncertain": ["취소 거래 전표입니다."],
    }

    async def fake_recognize(image_bytes: bytes, mime_type: str):
        return {
            "engine": "luna_low",
            "model": "gpt-6-luna",
            "reasoning_effort": "low",
            "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
            "request_id": "req_neg_test",
            "document": normalize(raw_negative),
            "raw_prediction": raw_negative,
            "confirmed": False,
        }

    monkeypatch.setattr(luna_pipeline, "recognize", fake_recognize)

    enq = client.post(
        "/v2/receipt-jobs?direction=purchase",
        headers=headers,
        files={"file": ("neg.png", img_bytes, "image/png")},
    )
    assert enq.status_code == 202
    receipt_id = enq.json()["receipt_id"]

    gen = app.dependency_overrides[get_session]()
    test_session: Session = next(gen)
    try:
        monkeypatch.setattr(worker, "engine", test_session.get_bind())
        assert worker.process_one() is True
    finally:
        gen.close()

    detail = client.get(f"/v2/receipts/{receipt_id}", headers=headers).json()
    assert detail["status"] == "done"
    assert detail["amount"] is None
    assert "amount" in detail["ocr_missing_fields"]
    assert any("음수·소수 금액" in w for w in detail["ocr_warnings"])
    assert detail["recognition"]["document"]["fields"]["payment_amount"] == -11000
    assert detail["recognition"]["document"]["fields"]["transaction_save_amount"] == -11000
    assert detail["recognition"]["document"]["fields"]["transaction_save_amount_source"] == "payment_amount"

    # Simulate ReceiptReviewEditor removeItem(0): item 1 shifts to index 0, item 2's parent_row shifts from 1 -> 0
    items_before = detail["recognition"]["document"]["items"]
    remove_idx = 0
    reindexed_items = [
        {
            **item,
            "parent_row": (
                None
                if item["parent_row"] is None or item["parent_row"] == remove_idx
                else item["parent_row"] - 1
                if item["parent_row"] > remove_idx
                else item["parent_row"]
            ),
        }
        for i, item in enumerate(items_before)
        if i != remove_idx
    ]
    assert len(reindexed_items) == 2
    assert reindexed_items[1]["parent_row"] == 0

    confirm_payload = {
        "vendor": "취소영수증카페",
        "amount": 5000,
        "date": "2026-10-13",
        "document": {
            "fields": {
                "vendor": "취소영수증카페",
                "branch": None,
                "business_number": "101-81-99999",
                "transaction_datetime": "2026-10-13 13:00:00",
                "printed_total_amount": 5000,
                "payment_amount": 5000,
                "supply_amount": 4545,
                "taxable_supply_amount": 4545,
                "vat_amount": 455,
                "tax_exempt_amount": None,
                "discount_amount": -1000,
                "subtotal_amount": 6000,
            },
            "items": reindexed_items,
        },
        "purpose": "고객 미팅 음료",
        "evidence_type": "card_receipt",
        "business_related": True,
        "tax_treatment": "standard",
    }
    conf_resp = client.post(f"/v2/receipts/{receipt_id}/confirm-extraction", headers=headers, json=confirm_payload)
    assert conf_resp.status_code == 200, conf_resp.text
    saved_doc = client.get(f"/v2/receipts/{receipt_id}", headers=headers).json()
    assert saved_doc["recognition"]["document"]["items"][1]["parent_row"] == 0
    assert saved_doc["recognition"]["original_document"]["fields"]["payment_amount"] == -11000


def test_e2e_sequential_queue_processing_with_isolated_fixtures(client, monkeypatch):
    """Scenario D: 3 rapid uploads queued simultaneously are processed sequentially by worker without lock collision."""
    from app.main import app
    from app.core.database import get_session

    headers = _register_user(client, monkeypatch, "queue3-e2e@example.com")
    # Self-contained synthetic fixtures: no private images or experiment outputs.
    case_ids = ["QUEUE_A", "QUEUE_B", "QUEUE_C"]
    raw_by_sha = {}
    saved_by_case = {}
    receipt_ids = []

    for idx, cid in enumerate(case_ids):
        saved = {"raw_prediction": {
            "h": {"vendor": f"가상상점{idx}", "branch": None, "business_number": None, "datetime": "2026-10-13 12:30:00"},
            "m": [{"role": "payment", "scope": "unknown", "label": "결제액", "value": 1000 + idx}],
            "i": [{"n": f"가상상품{idx}", "q": 1, "u": 1000 + idx, "p": 1000 + idx, "t": "item", "parent": None}],
            "uncertain": []}}
        saved_by_case[cid] = saved
        img_bytes = _make_png_bytes((100 + idx * 20, 150, 200))
        sha = hashlib.sha256(img_bytes).hexdigest()
        raw_by_sha[sha] = (cid, saved["raw_prediction"])
        enq = client.post(
            "/v2/receipt-jobs?direction=purchase",
            headers=headers,
            files={"file": (f"{cid}.png", img_bytes, "image/png")},
        )
        assert enq.status_code == 202
        receipt_ids.append(enq.json()["receipt_id"])

    async def fake_recognize(image_bytes: bytes, mime_type: str):
        sha = hashlib.sha256(image_bytes).hexdigest()
        cid, raw_pred = raw_by_sha[sha]
        return {
            "engine": "luna_low",
            "model": "gpt-6-luna",
            "reasoning_effort": "low",
            "image_sha256": sha,
            "request_id": f"req_{cid}",
            "document": normalize(raw_pred),
            "raw_prediction": raw_pred,
            "confirmed": False,
        }

    monkeypatch.setattr(luna_pipeline, "recognize", fake_recognize)

    gen = app.dependency_overrides[get_session]()
    test_session: Session = next(gen)
    try:
        monkeypatch.setattr(worker, "engine", test_session.get_bind())
        for _ in range(3):
            assert worker.process_one() is True
    finally:
        gen.close()

    r_kr02 = client.get(f"/v2/receipts/{receipt_ids[0]}", headers=headers).json()
    r_kr38 = client.get(f"/v2/receipts/{receipt_ids[1]}", headers=headers).json()
    r_kr44 = client.get(f"/v2/receipts/{receipt_ids[2]}", headers=headers).json()

    for cid, response in zip(case_ids, [r_kr02, r_kr38, r_kr44]):
        expected = normalize(saved_by_case[cid]["raw_prediction"])
        document = response["recognition"]["document"]
        assert response["status"] == "done"
        for key in (
            "vendor", "branch", "business_number", "transaction_datetime",
            "printed_total_amount", "payment_amount", "supply_amount", "vat_amount",
            "tax_exempt_amount", "discount_amount", "transaction_save_amount",
            "transaction_save_amount_source",
        ):
            assert document["fields"][key] == expected["fields"][key]
        assert document["items"] == expected["items"]
