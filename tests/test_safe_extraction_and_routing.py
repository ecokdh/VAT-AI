# -*- coding: utf-8 -*-
"""
Verification tests covering Section 2 & 3 mandatory requirements:
1. Subtotal vs Total role separation when discount exists (9000 total kept, not replaced by 10000 subtotal)
2. Safe receipt orientation guard (EXIF + aspect ratio guard, zero re-compression when unchanged)
3. Preserved raw vs suggested/calculated fields in ReceiptDetails
4. Runtime routing of suspicious fields & distinguishing unapplicable from passed
5. Refund/negative transaction preservation (not treated as OCR error)
6. Zero discount vs unprinted discount
7. Item deletion does NOT shift answers to remaining items
8. Stale lock file auto-recovery on dead process/crash
"""
import io
import time
from pathlib import Path
from PIL import Image

from app.receipts.image_utils import apply_safe_receipt_orientation
from app.receipts.routing_rules import (
    check_business_number_signal,
    check_amount_arithmetic_signal,
    route_suspicious_fields,
)
from app.receipts.luna_low_contract import normalize
from app.receipts.questions import canonical_answers, questions, validated_answers
from app.receipts.schemas import ReceiptDetails


def _make_image_bytes(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(255, 255, 255)).save(buf, format="JPEG")
    return buf.getvalue()


def test_subtotal_vs_total_with_discount_separation():
    """
    Scenario:
    Subtotal: 10,000
    Discount: 1,000
    Final Total: 9,000
    Payment: 9,000
    Verify that printed_total_amount stays 9,000 and is NOT replaced by 10,000 subtotal.
    """
    raw_doc = {
        "h": {"vendor": "할인테스트마트", "business_number": "123-45-67890", "datetime": "2026-10-15 12:00:00"},
        "m": [
            {"role": "subtotal", "scope": "all", "label": "소계", "value": 10000},
            {"role": "discount", "scope": "all", "label": "할인", "value": 1000},
            {"role": "total", "scope": "all", "label": "최종 합계", "value": 9000},
            {"role": "payment", "scope": "unknown", "label": "카드 결제", "value": 9000},
        ],
        "i": [],
        "uncertain": [],
    }
    normalized = normalize(raw_doc)
    fields = normalized["fields"]

    assert fields["printed_total_amount"] == 9000, f"Expected 9000, got {fields['printed_total_amount']}"
    assert fields["subtotal_amount"] == 10000, f"Expected 10000, got {fields['subtotal_amount']}"
    assert fields["discount_amount"] == 1000, f"Expected 1000, got {fields['discount_amount']}"
    assert fields["payment_amount"] == 9000, f"Expected 9000, got {fields['payment_amount']}"


def test_item_deletion_does_not_shift_answers():
    """
    Scenario:
    Original items: Item A (source_row=0), Item B (source_row=1).
    User answers: Item A is personal, Item B is business.
    User deletes Item A, so only Item B remains.
    Verify Item B keeps its business answer and does NOT inherit Item A's personal answer.
    """
    doc_initial = {
        "items": [
            {"name": "사탕", "row_type": "item", "source_row": 0},
            {"name": "복사용지", "row_type": "item", "source_row": 1},
        ]
    }
    answers_initial = {
        "use": "mixed",
        "item_use_src_0": "personal",
        "item_use_src_1": "business",
    }
    # Validate and canonicalize initial answers
    canonical_init = canonical_answers(doc_initial, answers_initial)
    assert canonical_init.get("item_use_src_0") == "personal"
    assert canonical_init.get("item_use_src_1") == "business"

    # Now Item A is deleted, only Item B remains (preserving its source_row=1)
    doc_after_deletion = {
        "items": [
            {"name": "복사용지", "row_type": "item", "source_row": 1},
        ]
    }
    # Questions regenerated for the edited document
    qs = questions(doc_after_deletion, answers_initial)
    assert len(qs) == 2  # 'use' + 1 item question
    assert qs[1]["id"] == "item_use_src_1"
    assert "복사용지" in qs[1]["label"]

    # Canonical answers for doc_after_deletion:
    # Item B's answer is 'business'. Item A's 'personal' is NOT shifted to Item B!
    canonical_after = canonical_answers(doc_after_deletion, answers_initial)
    assert canonical_after.get("item_use_src_1") == "business"
    assert "item_use_src_0" not in canonical_after
    assert canonical_after.get("item_use_0") is None or canonical_after.get("item_use_0") != "personal"


def test_safe_receipt_orientation_and_no_recompression():
    # 1. Extreme landscape receipt (ratio 2.0 >= 1.7) -> rotated 90 deg cw
    kr13_bytes = _make_image_bytes(1200, 600)
    out_b, meta = apply_safe_receipt_orientation(kr13_bytes)
    assert meta["rotation_applied_deg"] == 90
    assert meta["final_size"] == [600, 1200]
    assert meta["coordinate_space"] == "rotated_90_cw"
    assert meta["reason"] == "extreme_landscape_ratio_guard"
    assert meta["bytes_recompressed"] is True

    # 2. Normal table landscape receipt (ratio 1.37 < 1.7) -> strictly preserved without recompression
    kr05_bytes = _make_image_bytes(1439, 1052)
    out_b2, meta2 = apply_safe_receipt_orientation(kr05_bytes)
    assert meta2["rotation_applied_deg"] == 0
    assert meta2["final_size"] == [1439, 1052]
    assert meta2["reason"] == "normal_landscape_table_preserved"
    assert out_b2 == kr05_bytes  # EXACT identity of bytes, zero recompression!
    assert meta2["bytes_recompressed"] is False

    # 3. Standard portrait receipt
    portrait_bytes = _make_image_bytes(600, 1200)
    out_b3, meta3 = apply_safe_receipt_orientation(portrait_bytes)
    assert meta3["rotation_applied_deg"] == 0
    assert out_b3 == portrait_bytes
    assert meta3["bytes_recompressed"] is False


def test_receipt_details_preserves_separated_fields():
    details = ReceiptDetails(
        business_number="201-81-21515",
        raw_business_number="201-81-21515",
        suggested_business_number=None,
        raw_vendor="스타벅스",
        suggested_vendor="STARBUCKS",
        supply_amount=10000,
        vat_amount=1000,
        calculated_supply_amount=10455,
        calculated_vat_amount=1045,
        conflicting_candidates={"supply_amount": [10000, 10455]},
    )
    d = details.model_dump()
    assert d["raw_business_number"] == "201-81-21515"
    assert d["suggested_vendor"] == "STARBUCKS"
    assert d["calculated_supply_amount"] == 10455
    assert d["conflicting_candidates"] == {"supply_amount": [10000, 10455]}


def test_routing_rules_conditional_arithmetic_and_refunds():
    # 1. Negative refund transaction: valid refund, not flagged as OCR defect
    amt_refund = check_amount_arithmetic_signal(
        {"payment_amount": -15000, "printed_total_amount": -15000},
        conflicts=[]
    )
    assert any(a.get("is_refund") is True for a in amt_refund)
    assert not any(a.get("suspicious") is True for a in amt_refund)

    # 2. Arithmetic match where discount was already subtracted from supply
    # Total = 9000, Supply = 8182, VAT = 818. Total == Supply + VAT (diff 0)
    # Discount = 1000. Double-subtracting discount would fail, but our rule checks both!
    flags_disc = check_amount_arithmetic_signal(
        {
            "printed_total_amount": 9000,
            "supply_amount": 8182,
            "vat_amount": 818,
            "discount_amount": 1000,
        },
        conflicts=[]
    )
    assert not any("arithmetic_mismatch" in f.get("reason", "") for f in flags_disc)

    # 3. Unapplicable arithmetic check when supply/vat are absent
    clean_no_supply = {
        "fields": {
            "vendor": "단순영수증식당",
            "business_number": "101-86-12347",
            "transaction_datetime": "2024-05-01 12:00:00",
            "payment_amount": 11000,
            "printed_total_amount": 11000,
            "supply_amount": None,
            "vat_amount": None,
        },
        "conflicts": [],
        "uncertain": [],
    }
    routed = route_suspicious_fields(clean_no_supply, {"rotation_applied_deg": 0})
    assert routed["arithmetic_status"] == "unapplicable"


def test_zero_discount_vs_unprinted_discount():
    doc_with_zero = {
        "h": {"vendor": "상점", "datetime": "2026-10-15"},
        "m": [
            {"role": "total", "value": 5000},
            {"role": "discount", "value": 0},
        ],
        "i": [],
        "uncertain": [],
    }
    norm_zero = normalize(doc_with_zero)
    assert norm_zero["fields"]["discount_amount"] == 0

    doc_without_disc = {
        "h": {"vendor": "상점", "datetime": "2026-10-15"},
        "m": [{"role": "total", "value": 5000}],
        "i": [],
        "uncertain": [],
    }
    norm_no_disc = normalize(doc_without_disc)
    assert norm_no_disc["fields"]["discount_amount"] is None


def test_stale_lock_recovery(tmp_path, monkeypatch):
    from app.core.config import settings
    from app.receipts import luna_client

    fake_ledger = tmp_path / "test_budget.json"
    fake_lock = tmp_path / "test_budget.lock"
    # Create an artificially expired lock file from 5 minutes ago
    fake_lock.write_text("pid_99999", encoding="utf-8")
    old_mtime = time.time() - (settings.LUNA_TIMEOUT_SECONDS + 60.0)
    import os
    os.utime(fake_lock, (old_mtime, old_mtime))

    monkeypatch.setattr(settings, "LUNA_BUDGET_LEDGER_FILE", str(fake_ledger))

    # Calling recognize should automatically detect and unlink the stale lock file
    import asyncio
    try:
        asyncio.run(luna_client.recognize(b"not-an-image", "image/jpeg"))
    except luna_client.LunaFailure as exc:
        # Expected failure should be API_KEY_MISSING or UNSUPPORTED_IMAGE or similar, NOT RECOGNITION_BUSY!
        assert exc.code != "RECOGNITION_BUSY", "Stale lock was not cleared!"
