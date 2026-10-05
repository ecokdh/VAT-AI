import uuid
import json
from datetime import date

import pytest
from pydantic import ValidationError
from sqlmodel import Session, SQLModel, create_engine

import app.main  # register all database tables
from app.receipts.document import DocumentFacts
from app.common.exceptions import AppException
from app.receipts.models import Receipt
from app.receipts.schemas import ReceiptOcrUpdate, ReceiptConfirmIn
from app.receipts.service import update_ocr, confirm_receipt


@pytest.mark.parametrize("heading,total,expected", [
    ("반품 전표", -2000, "RETURN"),
    ("교환 전표", -2000, "RETURN"),
    ("취소 영수증", -2000, "CANCELLATION"),
    ("반품 전표", 2000, None),
    ("교환/환불 14일 이내 가능", -2000, None),
])
def test_adjustment_requires_heading_and_negative_total(heading, total, expected):
    from app.receipts.kie import TextBox, fill_from_boxes
    boxes = (TextBox(heading, 0, 0, 150, 20),
             TextBox("합계", 0, 100, 50, 20), TextBox(str(total), 300, 100, 70, 20),
             TextBox("부가세", 0, 200, 60, 20), TextBox("-182", 300, 200, 70, 20))
    result = fill_from_boxes({}, boxes)
    assert result["document"].get("adjustment_type") == expected
    if expected:
        assert result["transaction_amount"] == -2000
        assert result["vat_amount"] == -182
        assert result["money_evidence"]["transaction_amount"]["state"] == "READ"
        assert len(result["money_evidence"]["transaction_amount"]["boxes"]) == 2
    else:
        assert result.get("vat_amount") is None


def test_negative_coupon_and_conflicting_headings_do_not_authorize_adjustment():
    from app.receipts.kie import TextBox
    from app.receipts.metadata import extract_metadata
    heading = TextBox("반품전표", 0, 0, 150, 20)
    coupon = (TextBox("쿠폰할인", 0, 100, 80, 20), TextBox("-2000", 300, 100, 70, 20))
    assert "adjustment_type" not in extract_metadata((heading, *coupon))
    assert "adjustment_type" not in extract_metadata((heading, TextBox("합계할인 -2000", 0, 100, 150, 20)))
    conflict = extract_metadata((heading, TextBox("취소전표", 0, 50, 150, 20),
        TextBox("판매합계", 0, 150, 80, 20), TextBox("-2000", 300, 150, 70, 20)))
    assert "adjustment_type" not in conflict
    assert "conflicting_adjustment_type_candidates" in conflict["review_reasons"]


def test_refund_tax_row_does_not_conflict_with_signed_sales_total():
    from app.receipts.kie import TextBox, fill_from_boxes
    result = fill_from_boxes({}, (TextBox("교환전표", 0, 0, 150, 20),
        TextBox("과세", 0, 100, 40, 20), TextBox("합계", 60, 100, 40, 20),
        TextBox("1818", 300, 100, 70, 20), TextBox("판매", 0, 200, 40, 20),
        TextBox("합계", 60, 200, 40, 20), TextBox("-2000", 300, 200, 70, 20)))
    assert result["transaction_amount"] == -2000
    assert "conflicting_transaction_amount_candidates" not in result["review_reasons"]
    # Do not manufacture a minus sign on the positive OCR tax value.
    assert result.get("taxable_supply_amount") is None


@pytest.mark.parametrize("change", ["value", "raw", "source", "clear"])
def test_original_date_candidates_cannot_be_rewritten_by_manual_save(receipt_session, change):
    import copy
    session, receipt = receipt_session
    candidate = {"raw": "2026/10/05", "value": "2026-10-05", "source": {
        "kind": "ocr", "state": "UNREVIEWED", "confidence": .72,
        "boxes": [{"x": 10, "y": 20, "width": 100, "height": 18}]}}
    receipt.document_json = DocumentFacts(date_candidates=[candidate]).model_dump_json()
    session.add(receipt)
    session.commit()
    saved = update_ocr(session, receipt.user_id, receipt.id, ReceiptOcrUpdate(base_revision=receipt.revision,
        document=DocumentFacts(date_candidates=[candidate], supply_date="2026-10-05")))
    assert saved.document.date_candidates == [candidate]
    assert saved.document.supply_date == "2026-10-05"
    old_document = receipt.document_json
    changed = copy.deepcopy(candidate)
    if change == "value": changed["value"] = "2026-10-06"
    elif change == "raw": changed["raw"] = "edited original"
    elif change == "source": changed["source"]["confidence"] = 1
    with pytest.raises(AppException) as error:
        update_ocr(session, receipt.user_id, receipt.id, ReceiptOcrUpdate(base_revision=saved.revision,
            vendor="잘못된 수정", document=DocumentFacts(date_candidates=[] if change == "clear" else [changed])))
    assert error.value.status_code == 400
    session.refresh(receipt)
    assert receipt.revision == saved.revision and receipt.vendor == "상점"
    assert receipt.document_json == old_document


@pytest.mark.parametrize("field,value,reason", [
    ("customer_business_number", "123", "customer_business_number_format"),
    ("merchant_business_number", "12345ABCDE", "merchant_business_number_format"),
    ("merchant_business_number", "9876543210", "merchant_business_number_mismatch"),
])
def test_document_business_roles_validate_format_and_merchant_agreement(receipt_session, field, value, reason):
    from app.receipts.document import evidence_validation
    session, receipt = receipt_session
    receipt.business_number = "1234567890"
    document = DocumentFacts(document_type="TAX_INVOICE", document_issue_date="2026-10-05",
        merchant_business_number="1234567890", customer_business_number="9876543210")
    assert evidence_validation(receipt, document)["validation_status"] == "VALID"
    changed = DocumentFacts.model_validate(document.model_dump() | {field: value})
    result = evidence_validation(receipt, changed)
    assert result["validation_status"] == "CONFLICT" and reason in result["conflicts"]
    assert result["external_business_verification"] == "NOT_PERFORMED"
    assert result["deduction_status"] == "UNDETERMINED"


@pytest.fixture
def receipt_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'document.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        receipt = Receipt(user_id=uuid.uuid4(), image_url="local.png", vendor="상점",
                          date=date(2026, 10, 5), amount=11000, transaction_amount=11000,
                          taxable_supply_amount=10000, tax_exempt_amount=0, vat_amount=1000,
                          status="done", money_schema_version=2)
        session.add(receipt)
        session.commit()
        session.refresh(receipt)
        yield session, receipt


def test_structured_items_preserve_identity_through_name_and_order_changes(receipt_session):
    session, receipt = receipt_session
    first = update_ocr(session, receipt.user_id, receipt.id, ReceiptOcrUpdate(base_revision=1, line_items=[
        {"name": "반복 상품", "quantity": 0.5, "printed_unit_price": 1000, "line_amount": 400},
        {"name": "반복 상품", "line_amount": 200},
    ]))
    a, b = first.line_items
    assert a.id != b.id
    assert a.effective_unit_price == 800
    assert b.quantity is None and b.effective_unit_price is None
    renamed = a.model_dump(mode="json") | {"name": "수정 상품"}
    second = update_ocr(session, receipt.user_id, receipt.id, ReceiptOcrUpdate(
        base_revision=first.revision, line_items=[b.model_dump(mode="json"), renamed]))
    assert [item.id for item in second.line_items] == [b.id, a.id]
    assert second.line_items[1].original_name == "반복 상품"
    assert second.items == ["반복 상품", "수정 상품"]
    assert second.line_items[1].sources["name"].kind == "manual"


def test_unknown_item_id_rolls_back_revision_and_other_edits(receipt_session):
    session, receipt = receipt_session
    with pytest.raises(AppException):
        update_ocr(session, receipt.user_id, receipt.id, ReceiptOcrUpdate(
            base_revision=1, vendor="변경", line_items=[{"id": "another-receipt", "name": "상품"}]))
    session.refresh(receipt)
    assert receipt.revision == 1 and receipt.vendor == "상점"


def test_empty_item_value_states_are_explicit_and_cannot_forge_confidence(receipt_session):
    session, receipt = receipt_session
    saved = update_ocr(session, receipt.user_id, receipt.id, ReceiptOcrUpdate(base_revision=1,
        line_items=[{"name": "상품", "quantity": 2}]))
    item = saved.line_items[0].model_dump(mode="json")
    item["quantity"] = None
    cleared = update_ocr(session, receipt.user_id, receipt.id, ReceiptOcrUpdate(base_revision=saved.revision, line_items=[item]))
    assert cleared.line_items[0].sources["quantity"].state == "UNREVIEWED"
    item = cleared.line_items[0].model_dump(mode="json")
    item["sources"]["quantity"] = {"kind": "ocr", "state": "ABSENT", "confidence": 1}
    absent = update_ocr(session, receipt.user_id, receipt.id, ReceiptOcrUpdate(base_revision=cleared.revision, line_items=[item]))
    assert absent.line_items[0].sources["quantity"].kind == "manual"
    assert absent.line_items[0].sources["quantity"].state == "ABSENT"
    assert absent.line_items[0].sources["quantity"].confidence is None
    item["quantity"] = 2
    with pytest.raises(AppException):
        update_ocr(session, receipt.user_id, receipt.id, ReceiptOcrUpdate(base_revision=absent.revision, line_items=[item]))


def test_discount_scope_references_and_inclusion_are_validated(receipt_session):
    session, receipt = receipt_session
    saved = update_ocr(session, receipt.user_id, receipt.id, ReceiptOcrUpdate(base_revision=1, line_items=[{"name": "상품"}]))
    discount = {"id": "discount", "kind": "DISCOUNT", "scope": "GROUP", "amount": 100, "item_ids": [saved.line_items[0].id]}
    coupon = {"id": "coupon", "kind": "COUPON", "scope": "TRANSACTION", "amount": 50, "included_in_discount_id": "discount"}
    document = DocumentFacts(discounts=[discount, coupon])
    assert document.discounts[1].included_in_discount_id == "discount"
    with pytest.raises(ValidationError):
        DocumentFacts(discounts=[{**discount, "included_in_discount_id": "coupon"}, coupon])
    with pytest.raises(AppException):
        update_ocr(session, receipt.user_id, receipt.id, ReceiptOcrUpdate(base_revision=saved.revision,
            document={"discounts": [{**discount, "item_ids": ["other-receipt"]}]}))
    session.refresh(receipt)
    assert receipt.revision == saved.revision


def test_metadata_keeps_ambiguous_dates_candidates_and_masks_card_numbers():
    from app.receipts.kie import TextBox, fill_from_boxes
    from app.receipts.metadata import extract_metadata
    rows = ["신용카드 매출전표", "2026-10-05", "공급일 2026-10-04", "승인일시 2026-10-05 13:14:15",
            "승인번호 12345678", "카드번호 1234-5678-1234-9876", "고객 사업자번호 123-45-67890",
            "가맹점 사업자번호 987-65-43210"]
    boxes = tuple(TextBox(text, 0, i * 30, 300, 20, .9) for i, text in enumerate(rows))
    result = extract_metadata(boxes)
    assert result["document_type"] == "CARD_RECEIPT"
    assert result["supply_date"] == "2026-10-04"
    assert "document_issue_date" not in result
    assert result["payment_date"] == "2026-10-05"
    assert result["transaction_datetime"] == "2026-10-05T13:14:15"
    assert result["approval_number"] == "12345678"
    assert result["card_number_masked"] == "****-****-****-9876"
    assert result["card_last4"] == "9876"
    assert result["customer_business_number"] != result["merchant_business_number"]
    assert len(result["date_candidates"]) == 3
    assert extract_metadata((TextBox("카드번호 5461****", 0, 0, 300, 20),))["card_number_masked"] == "5461****"
    assert fill_from_boxes({}, boxes)["business_number"] == "9876543210"
    with pytest.raises(ValidationError):
        DocumentFacts(card_number_masked="1234-5678-1234-9876")
    with pytest.raises(ValidationError):
        DocumentFacts(supply_date="2026-02-30")


def test_stale_revision_cannot_confirm_changed_required_information(receipt_session):
    session, receipt = receipt_session
    update_ocr(session, receipt.user_id, receipt.id, ReceiptOcrUpdate(base_revision=1, vendor="새 상점"))
    with pytest.raises(AppException) as error:
        confirm_receipt(session, receipt.user_id, receipt.id, ReceiptConfirmIn(base_revision=1))
    assert error.value.status_code == 409
    session.refresh(receipt)
    assert receipt.confirmed is False


def test_revision_required_and_dual_item_inputs_rejected():
    with pytest.raises(ValidationError):
        ReceiptConfirmIn()
    with pytest.raises(ValidationError):
        ReceiptOcrUpdate(base_revision=1, items=["상품"], line_items=[{"name": "상품"}])


def test_missing_printed_item_numbers_do_not_invent_values_or_block_fact_confirmation(receipt_session):
    session, receipt = receipt_session
    saved = update_ocr(session, receipt.user_id, receipt.id, ReceiptOcrUpdate(
        base_revision=1, line_items=[{"name": "수량 미기재"}]))
    confirmed = confirm_receipt(session, receipt.user_id, receipt.id, ReceiptConfirmIn(base_revision=saved.revision))
    assert confirmed.confirmed is True
    assert confirmed.line_items[0].quantity is None
    assert confirmed.line_items[0].printed_unit_price is None
    assert confirmed.evidence_validation["deduction_status"] == "UNDETERMINED"


def test_partial_document_edit_preserves_other_facts_and_marks_manual_source(receipt_session):
    session, receipt = receipt_session
    first = update_ocr(session, receipt.user_id, receipt.id, ReceiptOcrUpdate(base_revision=1,
        document={"document_type": "CARD_RECEIPT", "approval_number": "12345678"}))
    second = update_ocr(session, receipt.user_id, receipt.id, ReceiptOcrUpdate(base_revision=first.revision,
        document={"purchase_purpose": "사무용"}))
    assert second.document.approval_number == "12345678"
    assert second.document.document_type == "CARD_RECEIPT"
    assert second.document.sources["purchase_purpose"].kind == "manual"


@pytest.mark.parametrize("invalid", ["2026-10-05", "2026-02-30T10:00:00", "2026-10-05T25:00:00", "2026-10-05T10:75:00", "2026-10-05T10:30:00 trailing"])
def test_transaction_datetime_rejects_invalid_or_dateless_candidates(invalid):
    with pytest.raises(ValidationError):
        ReceiptOcrUpdate(base_revision=1, document={"transaction_datetime": invalid})


def test_transaction_datetime_normalizes_separator_and_keeps_distinct_dates(receipt_session):
    session, receipt = receipt_session
    saved = update_ocr(session, receipt.user_id, receipt.id, ReceiptOcrUpdate(base_revision=1,
        document={"transaction_datetime": "2026-10-05 10:30", "supply_date": "2026-10-04", "payment_date": "2026-10-06"}))
    assert saved.document.transaction_datetime == "2026-10-05T10:30:00"
    assert saved.document.supply_date == "2026-10-04" and saved.document.payment_date == "2026-10-06"
    assert saved.document.document_issue_date is None
    assert DocumentFacts(transaction_datetime="2026-10-05T10:30:00Z").transaction_datetime == "2026-10-05T10:30:00+00:00"


@pytest.mark.parametrize("quantity,amount", [(5e-324, 1e308), (1e308, 5e-324)])
def test_unrepresentable_effective_price_keeps_partial_item_without_server_error(receipt_session, quantity, amount):
    session, receipt = receipt_session
    saved = update_ocr(session, receipt.user_id, receipt.id, ReceiptOcrUpdate(base_revision=1,
        line_items=[{"name": "부분 계산", "quantity": quantity, "printed_unit_price": 1000, "line_amount": amount}]))
    item = saved.line_items[0]
    assert item.quantity == quantity and item.line_amount == amount and item.printed_unit_price == 1000
    assert item.effective_unit_price is None and item.sources["effective_unit_price"].state == "FAILED"
    assert item.sources["effective_unit_price"].confidence is None and saved.revision == 2


def test_effective_price_provenance_uses_input_regions_without_ocr_confidence():
    from app.receipts.document import StructuredItem, complete_item
    item = complete_item(StructuredItem(name="중량 상품", quantity=.5, line_amount=400,
        sources={"quantity": {"kind": "ocr", "boxes": [{"x": 10, "y": 20, "width": 20, "height": 10}], "confidence": .9},
            "line_amount": {"kind": "ocr", "boxes": [{"x": 50, "y": 20, "width": 40, "height": 10}], "confidence": .8}}))
    assert item.effective_unit_price == 800
    assert [box.x for box in item.sources["effective_unit_price"].boxes] == [10, 50]
    assert item.sources["effective_unit_price"].kind == "calculated" and item.sources["effective_unit_price"].confidence is None


def test_general_receipt_heading_is_a_candidate_but_policy_notice_is_not():
    from app.receipts.kie import TextBox
    from app.receipts.metadata import extract_metadata
    assert extract_metadata((TextBox("<<< 영 수 증 >>>", 0, 0, 200, 20),))["document_type"] == "GENERAL_RECEIPT"
    assert "document_type" not in extract_metadata((TextBox("교환시 영수증을 지참하세요", 0, 0, 200, 20),))
    assert extract_metadata((TextBox("영수증", 0, 0, 100, 20), TextBox("신용카드 매출전표", 0, 50, 200, 20)))["document_type"] == "CARD_RECEIPT"


def test_coordinate_money_ignores_remote_next_array_token():
    from app.receipts.kie import TextBox, fill_from_boxes, financial_from_fields
    fields = [{"inferText": "합계", "boundingPoly": {"vertices": [{"x": 0, "y": 0}]}}, {"inferText": "5000"}]
    assert financial_from_fields(fields)["transaction_amount"] is None
    filled = fill_from_boxes({"amount": 5000}, (TextBox("합계", 0, 0, 50, 20),
        TextBox("18780", 200, 0, 60, 20), TextBox("5000", 200, 500, 60, 20)))
    assert filled["transaction_amount"] == 18780 and filled["amount"] == 18780


def test_money_evidence_is_tied_to_label_and_matching_number():
    from app.receipts.kie import TextBox, fill_from_boxes
    result = fill_from_boxes({}, (TextBox("합계", 0, 0, 50, 20, .95),
        TextBox("18780", 200, 0, 60, 20, .8), TextBox("18780", 200, 500, 60, 20, .5)))
    source = result["money_evidence"]["transaction_amount"]
    assert source["state"] == "READ" and source["confidence"] == .8
    assert len(source["boxes"]) == 2 and all(box["y"] == 0 for box in source["boxes"])
    missing = fill_from_boxes({}, (TextBox("부가세", 0, 0, 50, 20),))
    assert missing["money_evidence"]["vat_amount"]["state"] == "FAILED"
    assert missing["money_evidence"]["tax_exempt_amount"]["state"] == "UNREVIEWED"


def test_conflicting_coordinate_totals_are_preserved_as_review_reason():
    from app.receipts.kie import TextBox, fill_from_boxes
    filled = fill_from_boxes({"amount": 5000}, (TextBox("합계", 0, 0, 50, 20),
        TextBox("5000", 200, 0, 60, 20), TextBox("합계", 0, 200, 50, 20), TextBox("6000", 200, 200, 60, 20)))
    assert filled["transaction_amount"] is None and filled["amount"] is None
    assert "conflicting_transaction_amount_candidates" in filled["review_reasons"]


def test_printed_card_payment_uses_its_own_amount_and_source_regions():
    from app.receipts.kie import TextBox, fill_from_boxes
    result = fill_from_boxes({}, (TextBox("신용카드지불:", 0, 100, 120, 20, .95),
        TextBox("18,780", 250, 100, 80, 20, .8),
        TextBox("카드번호", 0, 500, 100, 20), TextBox("5461****", 250, 500, 80, 20),
        TextBox("받은포인트", 0, 600, 100, 20), TextBox("18780", 250, 600, 80, 20)))
    assert result["payment_amount"] == 18780
    source = result["money_evidence"]["payment_amount"]
    assert source["state"] == "READ" and source["confidence"] == .8
    assert len(source["boxes"]) == 2 and all(box["y"] == 100 for box in source["boxes"])
    assert result.get("transaction_amount") is None


@pytest.mark.parametrize("cash", [5000, 7000])
def test_split_cash_and_card_are_not_mistaken_for_whole_payment(cash):
    from app.receipts.kie import TextBox, fill_from_boxes, financial_from_fields
    boxes = (TextBox("신용카드지불", 0, 100, 120, 20), TextBox("5000", 250, 100, 80, 20),
        TextBox("현금지불", 0, 200, 120, 20), TextBox(str(cash), 250, 200, 80, 20))
    result = fill_from_boxes({}, boxes)
    assert result["payment_amount"] is None
    assert "conflicting_payment_amount_candidates" in result["review_reasons"]
    assert result["money_evidence"]["payment_amount"]["state"] == "UNREVIEWED"
    without_boxes = financial_from_fields([{"inferText": box.text} for box in boxes])
    assert without_boxes["payment_amount"] is None
    assert "conflicting_payment_amount_candidates" in without_boxes["review_reasons"]


def test_no_coordinate_financial_conflicts_are_not_resolved_by_label_order():
    from app.receipts.kie import financial_from_fields, fill_from_boxes
    fields = [{"name": "transaction_amount", "inferText": "5000"},
        {"inferText": "합계 6000"}]
    for ordered in (fields, list(reversed(fields))):
        result = fill_from_boxes(financial_from_fields(ordered), ())
        assert result["transaction_amount"] is None and result["amount"] is None
        assert "conflicting_transaction_amount_candidates" in result["review_reasons"]


def test_order_generic_total_remains_subtotal_beside_explicit_final_total():
    from app.receipts.ocr_client import parse_response
    rows = [("상호", "주문 상점", 0), ("거래일", "2026-10-05", 30),
        (None, "주문서", 60), (None, "합계 23400", 100),
        (None, "할인후합계 16400", 150), (None, "결제금액 16400", 200)]
    fields = [{"name": name, "inferText": text, "boundingPoly": {"vertices":
        [{"x": 0, "y": y}, {"x": 220, "y": y}, {"x": 220, "y": y + 20}, {"x": 0, "y": y + 20}]}}
        for name, text, y in rows]
    result = parse_response({"images": [{"fields": fields}]})
    assert result is not None
    assert result.subtotal_amount == 23400
    assert result.transaction_amount == result.payment_amount == 16400
    assert "conflicting_transaction_amount_candidates" not in result.review_reasons


def test_coordinate_items_keep_repeats_fractional_quantity_and_printed_price():
    from app.receipts.kie import TextBox, extract_line_items
    boxes = tuple(box for y in (100, 150) for box in (
        TextBox("상품", 0, y, 100, 20, .9, True), TextBox("1000", 300, y, 60, 20),
        TextBox("0.5", 400, y, 40, 20), TextBox("400", 500, y, 60, 20)))
    rows = extract_line_items(boxes)
    assert len(rows) == 2
    assert all(row["quantity"] == .5 and row["printed_unit_price"] == 1000 and row["line_amount"] == 400 for row in rows)
    assert rows[0]["sources"]["name"]["confidence"] == .9


def test_item_headers_determine_quantity_price_order_and_partial_fields():
    from app.receipts.kie import TextBox, extract_line_items
    rows = extract_line_items((TextBox("제품명", 0, 0, 100, 20),
        TextBox("수량", 300, 0, 60, 20), TextBox("단가", 400, 0, 60, 20), TextBox("금액", 500, 0, 80, 20),
        TextBox("휘발유", 0, 100, 100, 20), TextBox("11.567", 300, 100, 60, 20),
        TextBox("1729", 400, 100, 60, 20), TextBox("20000", 500, 100, 80, 20),
        TextBox("수량 판독 실패 상품", 0, 150, 200, 20), TextBox("1000", 400, 150, 60, 20), TextBox("2000", 500, 150, 80, 20),
        TextBox("금액만 읽힌 상품", 0, 200, 200, 20), TextBox("3000", 500, 200, 80, 20)))
    assert len(rows) == 3
    assert rows[0]["quantity"] == 11.567 and rows[0]["printed_unit_price"] == 1729
    assert rows[1]["quantity"] is None and rows[1]["printed_unit_price"] == 1000
    assert rows[2]["quantity"] is None and rows[2]["printed_unit_price"] is None and rows[2]["line_amount"] == 3000


def test_wrapped_names_barcode_and_repeated_indexed_items_keep_row_evidence():
    from app.receipts.kie import TextBox, extract_line_items
    boxes = (TextBox("품명", 0, 0, 100, 20), TextBox("단가", 300, 0, 60, 20),
        TextBox("수량", 400, 0, 60, 20), TextBox("금액", 500, 0, 80, 20),
        TextBox("001", 0, 100, 30, 20), TextBox("길게 인쇄된", 50, 100, 180, 20, .9),
        TextBox("상품 이름", 50, 125, 180, 20, .8), TextBox("$*2200000000071", 0, 150, 200, 20),
        TextBox("1000", 300, 150, 60, 20), TextBox("0.5", 400, 150, 60, 20), TextBox("500", 500, 150, 80, 20),
        TextBox("002", 0, 200, 30, 20), TextBox("길게 인쇄된", 50, 200, 180, 20),
        TextBox("상품 이름", 50, 225, 180, 20), TextBox("1000", 300, 250, 60, 20),
        TextBox("1", 400, 250, 60, 20), TextBox("1000", 500, 250, 80, 20),
        TextBox("총 구 매액", 0, 300, 150, 20), TextBox("1500", 500, 300, 80, 20))
    rows = extract_line_items(boxes)
    assert [row["name"] for row in rows] == ["길게 인쇄된 상품 이름"] * 2
    assert [row["quantity"] for row in rows] == [.5, 1]
    assert [row["line_amount"] for row in rows] == [500, 1000]
    assert len(rows[0]["sources"]["name"]["boxes"]) == 2
    assert rows[0]["sources"]["name"]["confidence"] == .8


def test_header_only_name_is_retained_and_ambiguous_two_numbers_do_not_invent_quantity():
    from app.receipts.kie import TextBox, extract_line_items
    partial = extract_line_items((TextBox("단가", 300, 0, 60, 20), TextBox("수량", 400, 0, 60, 20),
        TextBox("금액", 500, 0, 80, 20), TextBox("숫자 판독 불가 상품", 0, 100, 180, 20),
        TextBox("합계", 0, 150, 50, 20), TextBox("1000", 500, 150, 80, 20)))
    assert len(partial) == 1
    assert all(partial[0][field] is None for field in ("quantity", "printed_unit_price", "line_amount"))
    ambiguous = extract_line_items((TextBox("상품", 0, 0, 100, 20),
        TextBox("100", 300, 0, 60, 20), TextBox("1000", 500, 0, 80, 20)))
    assert ambiguous[0]["quantity"] is None and ambiguous[0]["printed_unit_price"] is None
    assert ambiguous[0]["line_amount"] == 1000


def test_post_amount_wrapped_names_keep_numeric_row_and_all_name_evidence():
    from app.receipts.kie import TextBox, extract_line_items
    rows = extract_line_items((TextBox("단가", 300, 0, 60, 20), TextBox("수량", 400, 0, 60, 20),
        TextBox("금액", 500, 0, 80, 20),
        TextBox("001", 0, 100, 30, 20), TextBox("긴 상품(", 50, 100, 180, 20, .9),
        TextBox("1000", 300, 100, 60, 20), TextBox("0.5", 400, 100, 60, 20), TextBox("500", 500, 100, 80, 20),
        TextBox("대용량 2kg)", 50, 125, 180, 20, .7),
        TextBox("002", 0, 175, 30, 20), TextBox("긴 상품(", 50, 175, 180, 20, .8),
        TextBox("1000", 300, 175, 60, 20), TextBox("1", 400, 175, 60, 20), TextBox("1000", 500, 175, 80, 20),
        TextBox("대용량 2kg)", 50, 200, 180, 20, .6)))
    assert [row["name"] for row in rows] == ["긴 상품( 대용량 2kg)"] * 2
    assert [row["quantity"] for row in rows] == [.5, 1]
    assert [row["line_amount"] for row in rows] == [500, 1000]
    assert [row["sources"]["name"]["confidence"] for row in rows] == [.7, .6]
    assert [b["y"] for b in rows[0]["sources"]["name"]["boxes"]] == [100, 125]
    assert rows[0]["sources"]["line_amount"]["boxes"][0]["y"] == 100


@pytest.mark.parametrize("continuation_x,continuation_y,indexed,barcode", [(50, 200, False, False), (180, 125, False, False), (50, 125, True, False), (50, 150, False, True)])
def test_open_name_does_not_absorb_distant_indexed_or_barcode_separated_partial_item(continuation_x, continuation_y, indexed, barcode):
    from app.receipts.kie import TextBox, extract_line_items
    boxes = [TextBox("단가", 300, 0, 60, 20), TextBox("수량", 400, 0, 60, 20), TextBox("금액", 500, 0, 80, 20),
        TextBox("상품A(", 50, 100, 180, 20), TextBox("1000", 300, 100, 60, 20), TextBox("1", 400, 100, 60, 20), TextBox("1000", 500, 100, 80, 20)]
    if barcode:
        boxes.append(TextBox("8800000000001", 0, 125, 180, 20))
    if indexed:
        boxes.append(TextBox("002", 0, continuation_y, 30, 20))
    boxes.append(TextBox("상품B)", continuation_x, continuation_y, 100, 20))
    rows = extract_line_items(tuple(boxes))
    assert len(rows) == 2 and [row["name"] for row in rows] == ["상품A(", "상품B)"]
    assert rows[0]["line_amount"] == 1000
    assert rows[1]["quantity"] is None and rows[1]["line_amount"] is None


def test_unreadable_and_conflicting_item_columns_keep_failed_evidence():
    from app.receipts.kie import TextBox, extract_line_items
    rows = extract_line_items((TextBox("단가", 300, 0, 60, 20), TextBox("수량", 400, 0, 60, 20),
        TextBox("금액", 500, 0, 80, 20), TextBox("상품", 0, 100, 100, 20),
        TextBox("1O00", 300, 100, 60, 20, .4), TextBox("1", 400, 100, 20, 20, .8),
        TextBox("2", 430, 100, 20, 20, .7), TextBox("1000", 500, 100, 80, 20)))
    assert len(rows) == 1 and rows[0]["name"] == "상품"
    assert rows[0]["quantity"] is None and rows[0]["printed_unit_price"] is None
    assert rows[0]["line_amount"] == 1000
    assert rows[0]["sources"]["printed_unit_price"]["state"] == "FAILED"
    assert rows[0]["sources"]["quantity"]["state"] == "FAILED"
    assert len(rows[0]["sources"]["quantity"]["boxes"]) == 2


def test_evaluation_never_counts_numeric_token_from_wrong_item_as_match():
    from app.receipts.evaluation import evaluate_record
    truth = {"id": "unit", "printed": {}, "line_items": [{"name": "A", "quantity": 1, "line_amount": 100}, {"name": "B", "quantity": 1, "line_amount": 200}]}
    _, items, record = evaluate_record(truth, {"line_items": [{"name": "A", "quantity": 1, "line_amount": 200}, {"name": "B", "quantity": 1, "line_amount": 100}]})
    assert items["line_amount"]["tp"] == 0
    assert items["line_amount"]["fp"] == 2 and items["line_amount"]["fn"] == 2
    assert record["row_link_counts"] == {"expected_rows": 2, "predicted_rows": 2, "matched_names": 2, "exact_rows": 0}
    errors = [row for row in record["item_field_errors"] if row["field"] == "line_amount"]
    assert [(row["expected_row"], row["predicted_row"], row["expected"], row["predicted"]) for row in errors] == [(0, 0, 100, 200), (1, 1, 200, 100)]
    assert record["correction_needed"] is True


def test_return_item_signed_quantity_and_amount_survive_response_projection(receipt_session):
    session, receipt = receipt_session
    saved = update_ocr(session, receipt.user_id, receipt.id, ReceiptOcrUpdate(base_revision=1,
        line_items=[{"name": "반품", "quantity": -1, "printed_unit_price": 2000, "line_amount": -2000}]))
    assert saved.line_items[0].quantity == -1
    assert saved.item_amounts[0].line_amount == -2000


def test_photo_requires_auth_and_owner(client, monkeypatch):
    from test_receipts import auth_headers, PNG_BYTES, successful_result
    from app.receipts import ocr_client
    async def fake_extract(*args):
        return successful_result()
    monkeypatch.setattr(ocr_client, "extract_receipt", fake_extract)
    owner = auth_headers(client)
    other = auth_headers(client, "other-photo@example.com")
    uploaded = client.post("/receipts", headers=owner, files={"file": ("receipt.png", PNG_BYTES, "image/png")}).json()
    path = f"/receipts/{uploaded['id']}/image"
    response = client.get(path, headers=owner)
    assert response.status_code == 200 and response.content == PNG_BYTES
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "private, no-store"
    assert client.get(path, headers=other).status_code == 404
    assert client.get(path).status_code == 401


def test_uploaded_refund_preserves_signed_calculation_and_confirmation(client, monkeypatch):
    from test_receipts import auth_headers, PNG_BYTES
    from app.receipts import ocr_client
    from app.receipts.kie import TextBox, fill_from_boxes
    # The provider response is mocked; this verifies local persistence, not real OCR accuracy.
    filled = fill_from_boxes({"vendor": "반품 상점", "date": date(2026, 10, 5)}, (TextBox("반품전표", 0, 0, 150, 20),
        TextBox("거래총액", 0, 100, 80, 20), TextBox("-2000", 300, 100, 70, 20),
        TextBox("면세금액", 0, 200, 80, 20), TextBox("0", 300, 200, 70, 20),
        TextBox("부가세", 0, 300, 80, 20), TextBox("-182", 300, 300, 70, 20)))
    async def fake_extract(*args):
        return ocr_client.OcrResult(vendor="반품 상점", date=date(2026, 10, 5),
            amount=-2000, transaction_amount=-2000, tax_exempt_amount=0, vat_amount=-182,
            ocr_raw="반품전표", document=filled["document"], money_evidence=filled["money_evidence"])
    monkeypatch.setattr(ocr_client, "extract_receipt", fake_extract)
    owner = auth_headers(client)
    response = client.post("/receipts", headers=owner, files={"file": ("refund.png", PNG_BYTES, "image/png")})
    assert response.status_code == 201
    saved = response.json()
    assert saved["transaction_amount"] == -2000 and saved["taxable_supply_amount"] == -1818
    assert saved["money_sources"]["taxable_supply_amount"]["kind"] == "calculated"
    assert saved["document"]["adjustment_type"] == "RETURN"
    original = json.loads(saved["ocr_original"])
    assert original["document"]["adjustment_type"] == "RETURN"
    assert original["money_evidence"]["transaction_amount"]["boxes"]
    confirmed = client.post(f"/receipts/{saved['id']}/ocr/confirm", headers=owner,
        json={"confirmed": True, "base_revision": saved["revision"]})
    assert confirmed.status_code == 200
    transaction = client.get(f"/transactions/{confirmed.json()['transaction_id']}", headers=owner)
    assert transaction.status_code == 200
    assert transaction.json()["workflow_status"] == "UNRESOLVED_ADJUSTMENT"


def test_storage_read_cannot_escape_root(tmp_path):
    from app.receipts.storage import LocalFileStorage
    root = tmp_path / "storage"
    root.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"secret")
    with pytest.raises(OSError):
        LocalFileStorage(root).read("../outside.png")


@pytest.mark.parametrize("state", ["ABSENT", "FAILED", "NOT_APPLICABLE", "UNREVIEWED"])
def test_money_empty_states_preserve_regions_without_fabricated_ocr_confidence(receipt_session, state):
    session, receipt = receipt_session
    region = {"x": 10, "y": 20, "width": 50, "height": 20}
    receipt.payment_amount = 11000
    receipt.money_sources_json = json.dumps({"payment_amount": {"kind": "printed", "state": "READ", "boxes": [region], "confidence": .9}})
    session.add(receipt)
    session.commit()
    saved = update_ocr(session, receipt.user_id, receipt.id, ReceiptOcrUpdate(base_revision=1,
        payment_amount=None, field_states={"payment_amount": state}))
    assert saved.payment_amount is None
    assert saved.money_sources["payment_amount"] == {"kind": "manual", "state": state, "boxes": [region], "confidence": None}
    assert saved.revision == 2


def test_explicit_missing_money_is_not_silently_refilled_by_calculation(receipt_session):
    session, receipt = receipt_session
    saved = update_ocr(session, receipt.user_id, receipt.id, ReceiptOcrUpdate(base_revision=1,
        tax_exempt_amount=None, field_states={"tax_exempt_amount": "ABSENT"}))
    assert saved.tax_exempt_amount is None and saved.money_sources["tax_exempt_amount"]["state"] == "ABSENT"
    with pytest.raises(AppException) as error:
        confirm_receipt(session, receipt.user_id, receipt.id, ReceiptConfirmIn(base_revision=saved.revision))
    assert error.value.status_code == 409
    with pytest.raises(AppException):
        update_ocr(session, receipt.user_id, receipt.id, ReceiptOcrUpdate(base_revision=saved.revision,
            field_states={"tax_exempt_amount": "READ"}))
    session.refresh(receipt)
    assert receipt.revision == saved.revision and not receipt.confirmed


def test_document_and_core_states_preserve_evidence_and_ignore_forged_confidence(receipt_session):
    session, receipt = receipt_session
    region = {"x": 10, "y": 20, "width": 50, "height": 20}
    receipt.document_json = DocumentFacts(approval_number="123", sources={
        "approval_number": {"kind": "ocr", "state": "READ", "boxes": [region], "confidence": .9},
        "business_number": {"kind": "ocr", "state": "UNREVIEWED", "boxes": [region]},
    }).model_dump_json()
    session.add(receipt)
    session.commit()
    saved = update_ocr(session, receipt.user_id, receipt.id, ReceiptOcrUpdate(base_revision=1,
        field_states={"business_number": "ABSENT"}, document=DocumentFacts(approval_number=None,
            sources={"approval_number": {"kind": "ocr", "state": "FAILED", "boxes": [], "confidence": 1}})))
    source = saved.document.sources["approval_number"]
    assert source.kind == "manual" and source.state == "FAILED" and source.confidence is None
    assert source.boxes[0].x == 10
    assert saved.document.sources["business_number"].state == "ABSENT"
    candidate = update_ocr(session, receipt.user_id, receipt.id, ReceiptOcrUpdate(base_revision=saved.revision,
        document=DocumentFacts(approval_number="maybe123", sources={"approval_number": {"kind": "ocr", "state": "UNREVIEWED", "confidence": 1}})))
    assert candidate.document.approval_number == "maybe123"
    assert candidate.document.sources["approval_number"].state == "UNREVIEWED"
    assert candidate.document.sources["approval_number"].kind == "manual"
    assert candidate.document.sources["approval_number"].confidence is None


def test_unknown_field_state_and_nonempty_absent_value_are_rejected(receipt_session):
    with pytest.raises(ValidationError):
        ReceiptOcrUpdate(base_revision=1, field_states={"unknown": "ABSENT"})
    session, receipt = receipt_session
    with pytest.raises(AppException):
        update_ocr(session, receipt.user_id, receipt.id, ReceiptOcrUpdate(base_revision=1,
            field_states={"vendor": "ABSENT"}))
    session.refresh(receipt)
    assert receipt.revision == 1 and receipt.vendor == "상점"


def test_unreviewed_required_candidate_cannot_be_confirmed_until_read(receipt_session):
    session, receipt = receipt_session
    saved = update_ocr(session, receipt.user_id, receipt.id, ReceiptOcrUpdate(base_revision=1,
        field_states={"vendor": "UNREVIEWED", "taxable_supply_amount": "UNREVIEWED"}))
    assert saved.vendor == "상점" and saved.taxable_supply_amount == 10000
    with pytest.raises(AppException) as error:
        confirm_receipt(session, receipt.user_id, receipt.id, ReceiptConfirmIn(base_revision=saved.revision))
    assert error.value.status_code == 409
    reviewed = update_ocr(session, receipt.user_id, receipt.id, ReceiptOcrUpdate(base_revision=saved.revision,
        field_states={"vendor": "READ", "taxable_supply_amount": "READ"}))
    assert confirm_receipt(session, receipt.user_id, receipt.id, ReceiptConfirmIn(base_revision=reviewed.revision)).confirmed


@pytest.mark.parametrize("field", ["vendor", "date", "business_number", "document_type", "approval_number",
    "document_issue_date", "customer_business_number", "taxable_supply_amount", "tax_exempt_amount", "vat_amount", "transaction_amount"])
def test_evidence_validation_requires_reviewed_required_candidates(receipt_session, field):
    from app.receipts.document import Evidence, evidence_validation
    session, receipt = receipt_session
    receipt.business_number = "1234567890"
    document = DocumentFacts(document_type="CARD_RECEIPT", approval_number="12345678")
    if field in ("document_issue_date", "customer_business_number"):
        document = DocumentFacts(document_type="TAX_INVOICE", document_issue_date="2026-10-05", customer_business_number="9876543210")
    assert evidence_validation(receipt, document)["validation_status"] == "VALID"
    if field in ("taxable_supply_amount", "tax_exempt_amount", "vat_amount", "transaction_amount"):
        receipt.money_sources_json = json.dumps({field: {"kind": "manual", "state": "UNREVIEWED"}})
    else:
        document.sources[field] = Evidence(kind="manual", state="UNREVIEWED")
    result = evidence_validation(receipt, document)
    assert result["validation_status"] == "INCOMPLETE"
    assert result["missing_fields"] == [field]
    assert result["unreviewed_fields"] == [field]
    assert result["deduction_status"] == "UNDETERMINED"
    assert result["conflicts"] == []
