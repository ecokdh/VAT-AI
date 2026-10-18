"""Regression tests for structure parsing, amount checks, reread, and budget."""
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.config import Settings
from app.receipts.amount_relations import check_amount_relations
from tests.budget_support import BudgetStop, ProviderBook, RunnerStop, accept_cached_response, reject_automatic_retry
from app.receipts.line_structure import (
    apply_user_item_edit,
    assemble_wrapped_rows,
    cache_identity,
    display_name,
    link_numbers_by_columns,
    parse_number,
    response_hash,
    structure_from_model,
    to_compact_raw,
)
from app.receipts.luna_low_contract import SCHEMA, normalize
from app.receipts.reread_decision import adopt_reread, box_status, map_crop_box_to_original, select_reread_plan
from app.receipts.relation_config import GCP_FLASH_PRICE_PER_1M, OPENAI_PRICE_PER_1M, STRUCTURE_VERSION


def _box(y0, y1, x0=0.1, x1=0.4):
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "space": "normalized_0_1"}


def _item(row_id, name, qty, unit, amount, y0=0.2, row_type="item", parent=None):
    return {
        "row_id": row_id,
        "raw_name": name,
        "display_name": display_name(name),
        "quantity": qty,
        "unit_price": unit,
        "line_amount": amount,
        "row_type": row_type,
        "parent_row_id": parent,
        "source_label": "품목",
        "box": _box(y0, y0 + 0.04),
        "uncertainty": [],
    }


def _adj(adj_id, role, value, *, scope="unknown", already=False, label=""):
    return {
        "adjustment_id": adj_id,
        "role": role,
        "scope": scope,
        "label": label or role,
        "value": value,
        "already_discounted": already,
        "box": _box(0.7, 0.74, 0.4, 0.8),
        "uncertainty": [],
    }


def _structure(rows, adjustments):
    return {"rows": rows, "adjustments": adjustments, "columns": [{"header": "수량", "role": "quantity"}], "store": {}, "uncertain": []}


def _by_rule(checks, rule_id):
    return [check for check in checks if check["rule_id"] == rule_id]


def test_default_extraction_path_stays_legacy():
    assert Settings.model_fields["RECEIPT_STRUCTURE_PATH"].default == "legacy"
    from app.receipts.line_structure import active_contract
    from app.receipts.luna_low_contract import CONTRACT_VERSION, PROMPT
    prompt, schema, version = active_contract()
    assert version == CONTRACT_VERSION
    assert schema == SCHEMA
    assert prompt == PROMPT


def test_structure_parser_keeps_raw_name_and_does_not_invent_amounts():
    parsed = structure_from_model({
        "store": {"vendor": "카페", "branch": None, "business_number": None, "datetime": None, "label": "상호"},
        "columns": [{"header": "상품명", "role": "name"}, {"header": "수량", "role": "quantity"}],
        "i": [
            {"row_id": "r000", "n": "아메리카노 1+1", "q": None, "u": None, "p": 3000, "t": "item", "parent": None, "source_label": "상품", "box": {"x0": 0.1, "y0": 0.2, "x1": 0.5, "y1": 0.25, "space": "normalized_0_1"}, "uncertainty": []},
            {"row_id": "dup", "n": "샷추가", "q": 1, "u": 500, "p": 500, "t": "option", "parent": 0, "source_label": "옵션", "box": {"x0": None, "y0": None, "x1": None, "y1": None, "space": "unknown"}, "uncertainty": []},
            {"row_id": "dup", "n": "8801234", "q": None, "u": None, "p": None, "t": "notice", "parent": None, "source_label": "코드", "box": {"x0": None, "y0": None, "x1": None, "y1": None, "space": "unknown"}, "uncertainty": []},
        ],
        "adjustments": [],
        "uncertain": [],
        "c": {"doc_type": "printed_receipt", "support_status": "supported", "issues": [], "affected_regions": [], "readable_summary": None, "reasoning": "인쇄 영수증"},
    })
    assert parsed["rows"][0]["raw_name"] == "아메리카노 1+1"
    assert parsed["rows"][0]["display_name"] == "아메리카노 1+1"
    assert parsed["rows"][0]["quantity"] is None
    assert parsed["rows"][1]["parent_row_id"] == "r000"
    assert parsed["rows"][2]["row_id"] != "dup"
    compact = to_compact_raw(parsed)
    assert all(item["t"] != "notice" for item in compact["i"])
    assert compact["i"][0]["q"] is None
    assert compact["i"][0]["u"] is None
    document = normalize(compact)
    assert document["fields"]["calculated_vat_amount"] is None or document["calculated_values"].get("calculated_vat_amount", {}).get("applied_to_extraction") is False


def test_column_link_ignores_near_numbers_outside_the_header():
    columns = [
        {"header": "상품", "role": "name", "x0": 0.05, "x1": 0.4},
        {"header": "수량", "role": "quantity", "x0": 0.45, "x1": 0.6},
        {"header": "금액", "role": "line_amount", "x0": 0.7, "x1": 0.95},
    ]
    cells = [
        {"text": "3kg", "x0": 0.1, "x1": 0.2, "y0": 0.3},
        {"text": "2", "x0": 0.48, "x1": 0.55, "y0": 0.3},
        {"text": "9,999", "x0": 0.2, "x1": 0.3, "y0": 0.31},
    ]
    linked = link_numbers_by_columns(columns, cells)
    assert linked[0]["column_role"] == "name"
    assert linked[1]["column_role"] == "quantity"
    assert linked[2]["column_role"] == "name"
    wrapped = assemble_wrapped_rows([
        {"text": "아주 긴 상품명", "column_role": "name", "x0": 0.1, "x1": 0.4, "y0": 0.2, "y1": 0.22},
        {"text": "2", "column_role": "quantity", "x0": 0.5, "x1": 0.55, "y0": 0.23, "y1": 0.25},
    ])
    assert wrapped[0]["continued"] is True
    assert wrapped[0]["raw_name"] == "아주 긴 상품명"


def test_discounted_subtotal_is_not_discounted_again():
    rows = [_item("r000", "핫도그", 1, 4900, 3430, 0.2), _item("r001", "음료", 1, 4100, 4100, 0.26)]
    rows[0]["inclusion"] = "included"
    before = _structure(rows, [
        _adj("a000", "subtotal", 9000, already=False, label="소계"),
        _adj("a001", "document_discount", 1470, label="할인"),
        _adj("a002", "total", 7530, label="합계"),
    ])
    bridge = _by_rule(check_amount_relations(before), "discount_bridge")[0]
    assert bridge["applied"] is True and bridge["status"] == "match"
    after = _structure(
        [_item("r000", "핫도그", 1, 4900, 3430), _item("r001", "음료", 1, 4100, 4100)],
        [_adj("a000", "subtotal", 7530, already=True, label="합계금액"), _adj("a001", "document_discount", 1470), _adj("a002", "total", 7530)],
    )
    again = _by_rule(check_amount_relations(after), "discount_bridge")[0]
    assert again["applied"] is True and again["status"] == "match"
    assert "다시 빼지 않음" in again["diagnosis"]


def test_empty_item_list_is_not_summed_as_zero():
    empty = _structure([], [_adj("a000", "subtotal", 5300, already=True, label="소계")])
    check = _by_rule(check_amount_relations(empty), "item_sum_subtotal")[0]
    assert check["applied"] is False
    assert check["status"] == "incomputable"
    assert check["reread"] is False
    assert "item_sum" not in check["evidence"]
    present = _structure([_item("r000", "김밥", 1, 5300, 5300)], [_adj("a000", "subtotal", 5300, already=True)])
    matched = _by_rule(check_amount_relations(present), "item_sum_subtotal")[0]
    assert matched["applied"] is True and matched["status"] == "match"


def test_line_amount_before_and_after_discount_and_fractional_values():
    mismatch = _structure([_item("r000", "핫도그", 1, 4900, 3430)], [_adj("a000", "subtotal", 3430, already=True)])
    line = _by_rule(check_amount_relations(mismatch), "line_qty_unit")[0]
    assert line["status"] == "mismatch" and line["reread"] is True
    fractional = _structure([_item("r000", "고기", Decimal("1.5"), 2000, 3000)], [])
    assert _by_rule(check_amount_relations(fractional), "line_qty_unit")[0]["status"] == "match"
    assert parse_number("1.5") == Decimal("1.5")
    negative = _structure([_item("r000", "반품", -1, 1000, -1000)], [])
    assert _by_rule(check_amount_relations(negative), "line_qty_unit")[0]["status"] == "match"
    zero = _structure([_item("r000", "증정", 0, 1000, 0)], [])
    assert _by_rule(check_amount_relations(zero), "line_qty_unit")[0]["status"] == "match"
    missing = _structure([_item("r000", "누락", None, 1000, 1000)], [])
    missing_check = _by_rule(check_amount_relations(missing), "line_qty_unit")[0]
    assert missing_check["status"] == "incomputable" and missing_check["applied"] is False


def test_mixed_tax_split_tender_and_points_are_not_collapsed():
    mixed = _structure([], [
        _adj("a000", "supply", 5000, scope="taxable"),
        _adj("a001", "vat", 500),
        _adj("a002", "exempt", 2000),
        _adj("a003", "total", 7500),
    ])
    tax = _by_rule(check_amount_relations(mixed), "tax_composition")[0]
    assert tax["applied"] is True and tax["status"] == "match"
    overall = _structure([], [
        _adj("a000", "supply", 7000, scope="all"),
        _adj("a001", "vat", 500),
        _adj("a002", "total", 7500),
    ])
    assert _by_rule(check_amount_relations(overall), "tax_composition")[0]["status"] == "match"
    unknown_scope = _structure([], [
        _adj("a000", "supply", 5000, scope="taxable"),
        _adj("a001", "vat", 500),
        _adj("a002", "total", 5500),
    ])
    assert _by_rule(check_amount_relations(unknown_scope), "tax_composition")[0]["status"] == "incomputable"
    tender = _structure([], [
        _adj("a000", "tendered", 10000, label="받은돈"),
        _adj("a001", "change", 2000, label="거스름돈"),
        _adj("a002", "payment", 8000, label="카드"),
        _adj("a003", "points", 500, label="포인트"),
    ])
    paid = _by_rule(check_amount_relations(tender), "tender_composition")[0]
    assert paid["status"] == "match"
    assert "500" not in str(paid["evidence"].get("expected"))


def test_repeated_items_and_option_parent_are_kept_distinct():
    rows = [
        _item("r000", "김밥", 1, 3000, 3000, 0.2),
        _item("r001", "김밥", 1, 3000, 3000, 0.26),
        _item("r002", "쿠폰", None, None, -500, 0.32, row_type="discount", parent="r000"),
    ]
    rows[2]["inclusion"] = None
    checks = check_amount_relations(_structure(rows, []))
    duplicate = [check for check in checks if check["evidence"].get("possible_duplicate")]
    assert duplicate and duplicate[0]["reread"] is True
    link = _by_rule(checks, "option_link")[0]
    assert link["status"] == "incomputable"
    assert rows[0]["row_id"] != rows[1]["row_id"]


def test_bad_crop_hash_and_user_edit_preserve_model_rows():
    assert box_status({"x0": -0.1, "y0": 0, "x1": 0.2, "y1": 0.2, "space": "normalized_0_1", "source": "model"}, 100, 200) == "out_of_range"
    assert box_status({"x0": 0, "y0": 0, "x1": 150, "y1": 2, "space": "pixels", "source": "model"}, 100, 200) == "out_of_range"
    mapped = map_crop_box_to_original({"x0": 0.2, "y0": 0.2, "x1": 0.6, "y1": 0.6}, {"x0": 0, "y0": 0, "x1": 1, "y1": 1})
    assert mapped["x0"] == pytest.approx(0.2) and mapped["x1"] == pytest.approx(0.6)
    assert map_crop_box_to_original({"x0": 0.2, "y0": 0.2, "x1": 0.6, "y1": 0.6}, {"x0": 0, "y0": 0, "x1": 1.2, "y1": 1}) is None
    body = {"n": "김밥", "q": 1}
    assert response_hash(body) == response_hash({"q": 1, "n": "김밥"})
    cached = {"identity": "abc", "response_hash": "nope", "stored_hash": "other", "body": body}
    with pytest.raises(RunnerStop):
        accept_cached_response(cached, "abc")
    document = {"model_rows": [_item("r000", "김밥", 1, 3000, 3000)], "working_rows": [_item("r000", "김밥", 1, 3000, 3000), _item("r001", "옵션", 1, 500, 500, parent="r000")], "user_edits": []}
    document["working_rows"][1]["purpose_id"] = "meal"
    apply_user_item_edit(document, {"op": "delete", "row_id": "r000"})
    assert document["model_rows"][0]["raw_name"] == "김밥"
    assert document["working_rows"][0]["parent_row_id"] is None
    assert document["working_rows"][0]["purpose_id"] == "meal"
    apply_user_item_edit(document, {"op": "add", "purpose_id": "supply", "row": {"raw_name": "추가", "row_type": "item"}})
    assert document["working_rows"][-1]["origin"] == "user_edit"
    assert document["model_rows"][0]["row_id"] == "r000"


def test_document_level_reread_uses_full_photo_not_keep_b():
    structure = _structure([_item("r000", "김밥", 1, 1000, 1000, 0.2)], [])
    plan = select_reread_plan(structure, [{
        "rule_id": "discount_bridge",
        "rows": ["a1"],
        "reread": True,
        "diagnosis": "최종 합계와 다름",
    }], (1000, 2000))
    assert plan["case_action"] == "reread"
    assert plan["regions"][0]["mode"] == "full_photo"
    assert plan["regions"][0]["crop"] is None
    assert len(plan["regions"]) == 1
    quiet = select_reread_plan(structure, [{"reread": False, "rows": ["a1"]}], (1000, 2000))
    assert quiet["case_action"] == "keep_b"


def test_adoption_holds_weak_evidence_and_keeps_other_rows():
    structure = _structure([
        _item("r000", "김밥", 1, 3000, 2500, 0.2),
        _item("r001", "라면", 1, 4000, 4000, 0.3),
    ], [])
    plan = select_reread_plan(structure, check_amount_relations(structure), (1000, 2000))
    assert plan["case_action"] == "reread"
    assert len(plan["regions"]) <= 3
    region = plan["regions"][0]
    held = adopt_reread(structure, region, {"status": "success", "rows": [{"row_id": "r000", "n": "김밥", "q": 1, "u": 3000, "p": 3000, "checksum_only": True}]})
    assert held["decision"] == "hold"
    assert held["rows"][0]["line_amount"] == 2500
    adopted = adopt_reread(structure, region, {"status": "success", "rows": [{
        "row_id": "r000", "n": "김밥", "q": 1, "u": 3000, "p": 3000, "t": "item",
        "source_label": "행금액", "relation_note": "수량 1, 단가 3000, 행금액 3000이 같은 행에 인쇄됨",
    }]})
    assert adopted["decision"] == "adopt"
    assert adopted["changed_row_ids"] == ["r000"]
    assert adopted["rows"][1]["line_amount"] == 4000
    assert structure["rows"][0]["line_amount"] == 2500


def test_budget_stops_releases_and_resumes(tmp_path: Path):
    book = ProviderBook(tmp_path / "openai.json", "openai", Decimal("100"), external_measured=Decimal("40"), external_unsettled=Decimal("20"), krw_per_usd=Decimal("2200"))
    maximum = book.maximum_cost(1_000_000, 0, OPENAI_PRICE_PER_1M)
    assert maximum == Decimal("275")
    entry = book.reserve("case-a", Decimal("30"))
    assert book.remaining() == Decimal("10")
    with pytest.raises(BudgetStop):
        book.reserve("case-b", Decimal("11"))
    book.release_before_http(entry["attempt_id"], "no_http")
    assert book.remaining() == Decimal("40")
    again = book.reserve("case-a", Decimal("25"))
    book.fail_after_http(again["attempt_id"], "http_429", usage_known=False)
    assert book.snapshot()["this_run_unsettled_krw"] == pytest.approx(25)
    assert book.resume_open()[0]["attempt_id"] == again["attempt_id"]
    book.settle(again["attempt_id"], Decimal("10"))
    assert book.snapshot()["remaining_krw"] == pytest.approx(30)
    with pytest.raises(RunnerStop):
        reject_automatic_retry(True)
    flash = ProviderBook(tmp_path / "gcp.json", "gcp", Decimal("10000"), krw_per_usd=Decimal("1595"))
    reserved = flash.maximum_cost(8000, 4000, GCP_FLASH_PRICE_PER_1M)
    assert reserved > 0
    identity = cache_identity(image_sha256="abc", model="gpt-6-luna", prompt="one", schema={"a": 1}, version=STRUCTURE_VERSION)
    other = cache_identity(image_sha256="abc", model="gpt-6-luna", prompt="two", schema={"a": 1}, version=STRUCTURE_VERSION)
    assert identity != other
