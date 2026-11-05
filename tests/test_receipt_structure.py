"""Regression tests for receipt structure parsing."""

from app.core.config import Settings
from app.receipts.ocr.line_structure import (
    assemble_wrapped_rows,
    link_numbers_by_columns,
    structure_from_model,
    to_compact_raw,
)
from app.receipts.ocr.luna_low_contract import SCHEMA, normalize


def test_default_extraction_path_stays_legacy():
    assert Settings.model_fields["RECEIPT_STRUCTURE_PATH"].default == "legacy"
    from app.receipts.ocr.line_structure import active_contract
    from app.receipts.ocr.luna_low_contract import CONTRACT_VERSION, PROMPT
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
