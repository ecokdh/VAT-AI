"""Programmatic amount-relation checks. A match is not treated as truth.

A rule runs only when the role, scope, and whether a discount is already
included are known. Missing amounts stay missing. Printed numbers are not
rewritten to satisfy an equation.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.receipts.line_structure import parse_number
from app.receipts.relation_config import (
    ABSOLUTE_MONEY_TOLERANCE,
    ABSOLUTE_QUANTITY_TOLERANCE,
    RELATION_RULES,
    RULESET_VERSION,
)


def _result(rule_id: str, *, rows: list[str], fields: list[str], evidence: dict, applied: bool,
            status: str, diagnosis: str, reread: bool = False) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "version": RULESET_VERSION,
        "rows": rows,
        "fields": fields,
        "evidence": evidence,
        "applied": applied,
        "status": status,
        "mismatch": status == "mismatch",
        "reread": bool(reread),
        "diagnosis": diagnosis,
    }


def _close(left: Decimal, right: Decimal, tolerance: Decimal = ABSOLUTE_MONEY_TOLERANCE) -> bool:
    return abs(left - right) <= tolerance


def _enabled(rule_id: str) -> bool:
    return bool(RELATION_RULES.get(rule_id, {}).get("enabled"))


def _adjustments(structure: dict, role: str) -> list[dict]:
    return [row for row in structure.get("adjustments") or [] if row.get("role") == role]


def _known_amount(row: dict) -> Decimal | None:
    return parse_number(row.get("value"))


def check_amount_relations(structure: dict[str, Any]) -> list[dict[str, Any]]:
    checks = [
        _line_products(structure),
        _option_links(structure),
        _item_sum(structure),
        _discount_bridge(structure),
        _tax(structure),
        _tender(structure),
        _anomalies(structure),
    ]
    flat: list[dict[str, Any]] = []
    for item in checks:
        if isinstance(item, list):
            flat.extend(item)
        elif item is not None:
            flat.append(item)
    return flat


def _line_products(structure: dict) -> list[dict]:
    results = []
    if not _enabled("line_qty_unit"):
        return results
    for row in structure.get("rows") or []:
        if row.get("row_type") not in {"item", "option"}:
            continue
        quantity = parse_number(row.get("quantity"))
        unit = parse_number(row.get("unit_price"))
        amount = parse_number(row.get("line_amount"))
        evidence = {"quantity": _plain(quantity), "unit_price": _plain(unit), "line_amount": _plain(amount)}
        fields = ["quantity", "unit_price", "line_amount"]
        if quantity is None or unit is None or amount is None:
            results.append(_result(
                "line_qty_unit", rows=[row["row_id"]], fields=fields, evidence=evidence, applied=False,
                status="incomputable", diagnosis="수량·단가·행 금액 중 인쇄되지 않은 값이 있어 곱셈을 적용하지 않음",
            ))
            continue
        product = quantity * unit
        matched = _close(product, amount)
        results.append(_result(
            "line_qty_unit", rows=[row["row_id"]], fields=fields,
            evidence={**evidence, "product": _plain(product)}, applied=True,
            status="match" if matched else "mismatch", reread=not matched,
            diagnosis="인쇄 수량과 단가의 곱이 행 금액과 같음" if matched else "인쇄 수량과 단가의 곱이 행 금액과 다름. 인쇄값을 고치지 않음",
        ))
    return results


def _option_links(structure: dict) -> list[dict]:
    results = []
    if not _enabled("option_link"):
        return results
    rows = {row["row_id"]: row for row in structure.get("rows") or []}
    for row in structure.get("rows") or []:
        if row.get("row_type") not in {"option", "discount"}:
            continue
        parent_id = row.get("parent_row_id")
        parent = rows.get(parent_id) if parent_id else None
        if parent is None:
            results.append(_result(
                "option_link", rows=[row["row_id"]], fields=["parent_row_id"],
                evidence={"parent_row_id": parent_id}, applied=False, status="incomputable",
                diagnosis="옵션·할인 행의 소속 상품이 확인되지 않음", reread=True,
            ))
            continue
        inclusion = row.get("inclusion")
        if inclusion not in {"extra", "included"}:
            results.append(_result(
                "option_link", rows=[row["row_id"], parent_id], fields=["line_amount", "inclusion"],
                evidence={"parent_row_id": parent_id, "inclusion": inclusion}, applied=False,
                status="incomputable", diagnosis="옵션·할인 금액이 상품 금액에 포함됐는지 확인되지 않아 빼거나 더하지 않음",
            ))
            continue
        child_amount = parse_number(row.get("line_amount"))
        parent_amount = parse_number(parent.get("line_amount"))
        if child_amount is None or parent_amount is None:
            results.append(_result(
                "option_link", rows=[row["row_id"], parent_id], fields=["line_amount"],
                evidence={"inclusion": inclusion}, applied=False, status="incomputable",
                diagnosis="포함 관계는 알지만 금액이 비어 있어 계산하지 않음",
            ))
            continue
        results.append(_result(
            "option_link", rows=[row["row_id"], parent_id], fields=["line_amount", "inclusion"],
            evidence={"inclusion": inclusion, "child": _plain(child_amount), "parent": _plain(parent_amount)},
            applied=True, status="match",
            diagnosis="별도 금액" if inclusion == "extra" else "상품 금액에 포함된 금액으로 표시됨. 다시 빼지 않음",
        ))
    return results


def _item_sum(structure: dict) -> dict:
    if not _enabled("item_sum_subtotal"):
        return _result("item_sum_subtotal", rows=[], fields=[], evidence={}, applied=False, status="incomputable", diagnosis="규칙 꺼짐")
    subtotals = _adjustments(structure, "subtotal")
    known = [(row, _known_amount(row)) for row in subtotals]
    present = [(row, amount) for row, amount in known if amount is not None]
    if len(present) != 1:
        return _result(
            "item_sum_subtotal", rows=[row["adjustment_id"] for row, _ in present], fields=["subtotal"],
            evidence={"subtotal_count": len(present)}, applied=False, status="incomputable",
            diagnosis="비교할 인쇄 소계가 하나만 확인되지 않음",
        )
    subtotal_row, subtotal = present[0]
    if subtotal_row.get("already_discounted") not in {True, False}:
        return _result("item_sum_subtotal", rows=[subtotal_row["adjustment_id"]], fields=["subtotal"], evidence={}, applied=False, status="incomputable", diagnosis="소계의 할인 반영 여부가 확인되지 않음")
    items = [row for row in structure.get("rows") or [] if row.get("row_type") == "item"]
    amounts = []
    for row in items:
        amount = parse_number(row.get("line_amount"))
        if amount is None:
            return _result(
                "item_sum_subtotal", rows=[row["row_id"]], fields=["line_amount", "subtotal"],
                evidence={"subtotal": _plain(subtotal)}, applied=False, status="incomputable",
                diagnosis="품목 행 금액이 비어 있어 0으로 두고 합산하지 않음",
            )
        amounts.append(amount)
    for row in structure.get("rows") or []:
        if row.get("row_type") in {"option", "discount"} and row.get("inclusion") not in {"extra", "included"}:
            return _result(
                "item_sum_subtotal", rows=[row["row_id"]], fields=["inclusion"],
                evidence={}, applied=False, status="incomputable",
                diagnosis="옵션·할인이 품목 합계에 들어가는지 확인되지 않음",
            )
    extras = []
    for row in structure.get("rows") or []:
        if row.get("row_type") == "option" and row.get("inclusion") == "extra":
            amount = parse_number(row.get("line_amount"))
            if amount is None:
                return _result("item_sum_subtotal", rows=[row["row_id"]], fields=["line_amount"], evidence={}, applied=False, status="incomputable", diagnosis="별도 옵션 금액이 비어 있음")
            extras.append(amount)
        if row.get("row_type") == "discount" and row.get("inclusion") == "extra" and not subtotal_row.get("already_discounted"):
            amount = parse_number(row.get("line_amount"))
            if amount is None:
                return _result("item_sum_subtotal", rows=[row["row_id"]], fields=["line_amount"], evidence={}, applied=False, status="incomputable", diagnosis="별도 할인 금액이 비어 있음")
            extras.append(amount)
    if not amounts and not extras:
        return _result(
            "item_sum_subtotal",
            rows=[subtotal_row["adjustment_id"]],
            fields=["line_amount", "subtotal"],
            evidence={"subtotal": _plain(subtotal), "printed_item_amounts": 0},
            applied=False,
            status="incomputable",
            diagnosis="인쇄된 품목 금액이 없어 0으로 합산하지 않음",
        )
    total = sum(amounts, Decimal("0")) + sum(extras, Decimal("0"))
    matched = _close(total, subtotal)
    return _result(
        "item_sum_subtotal",
        rows=[row["row_id"] for row in items] + [subtotal_row["adjustment_id"]],
        fields=["line_amount", "subtotal"],
        evidence={"item_sum": _plain(total), "subtotal": _plain(subtotal), "already_discounted": subtotal_row.get("already_discounted")},
        applied=True, status="match" if matched else "mismatch", reread=not matched,
        diagnosis="품목 합계가 인쇄 소계와 같음" if matched else "품목 합계가 인쇄 소계와 다름",
    )


def _discount_bridge(structure: dict) -> dict:
    if not _enabled("discount_bridge"):
        return _result("discount_bridge", rows=[], fields=[], evidence={}, applied=False, status="incomputable", diagnosis="규칙 꺼짐")
    subtotals = [row for row in _adjustments(structure, "subtotal") if _known_amount(row) is not None]
    totals = [row for row in _adjustments(structure, "total") if _known_amount(row) is not None]
    if len(subtotals) != 1 or len(totals) != 1:
        return _result("discount_bridge", rows=[], fields=["subtotal", "total"], evidence={}, applied=False, status="incomputable", diagnosis="소계와 최종 합계가 하나씩 확인되지 않음")
    subtotal_row, total_row = subtotals[0], totals[0]
    if subtotal_row.get("already_discounted") not in {True, False}:
        return _result("discount_bridge", rows=[subtotal_row["adjustment_id"]], fields=["already_discounted"], evidence={}, applied=False, status="incomputable", diagnosis="소계의 할인 반영 여부가 확인되지 않음")
    discounts = [row for row in _adjustments(structure, "document_discount")]
    surcharges = [row for row in _adjustments(structure, "surcharge")]
    if any(_known_amount(row) is None for row in discounts + surcharges):
        return _result("discount_bridge", rows=[], fields=["discount", "surcharge"], evidence={}, applied=False, status="incomputable", diagnosis="할인 또는 추가금액이 비어 있어 0으로 두지 않음")
    item_discounts = [row for row in structure.get("rows") or [] if row.get("row_type") == "discount"]
    if item_discounts and any(row.get("inclusion") not in {"extra", "included"} for row in item_discounts):
        return _result("discount_bridge", rows=[row["row_id"] for row in item_discounts], fields=["inclusion"], evidence={}, applied=False, status="incomputable", diagnosis="상품별 할인이 이미 반영됐는지 확인되지 않아 문서 할인에서 다시 빼지 않음")
    if any(row.get("inclusion") == "included" for row in item_discounts) and not subtotal_row.get("already_discounted"):
        return _result("discount_bridge", rows=[row["row_id"] for row in item_discounts], fields=["inclusion"], evidence={}, applied=False, status="incomputable", diagnosis="포함된 상품 할인과 할인 전 소계를 한 식에 섞지 않음")
    if not subtotal_row.get("already_discounted") and not discounts:
        return _result("discount_bridge", rows=[subtotal_row["adjustment_id"], total_row["adjustment_id"]], fields=["document_discount"], evidence={}, applied=False, status="incomputable", diagnosis="인쇄된 문서 할인이 없어 소계와 최종 합계를 같은 금액으로 단정하지 않음")
    discount_sum = sum((_known_amount(row) or Decimal("0")) for row in discounts) if not subtotal_row.get("already_discounted") else Decimal("0")
    if subtotal_row.get("already_discounted"):
        diagnosis_extra = "소계가 이미 할인 반영분이므로 문서 할인을 다시 빼지 않음"
    else:
        diagnosis_extra = "할인 전 소계에서 인쇄된 문서 할인만 한 번 뺌"
    if surcharges:
        diagnosis_extra += ". 인쇄된 추가금액만 더함"
        surcharge_sum = sum((_known_amount(row) or Decimal("0")) for row in surcharges)
    else:
        diagnosis_extra += ". 추가금액 행이 없어 그 항은 식에 넣지 않음"
        surcharge_sum = Decimal("0")
    expected = _known_amount(subtotal_row) - discount_sum + surcharge_sum
    actual = _known_amount(total_row)
    matched = _close(expected, actual)
    return _result(
        "discount_bridge",
        rows=[subtotal_row["adjustment_id"], total_row["adjustment_id"]],
        fields=["subtotal", "document_discount", "surcharge", "total"],
        evidence={"expected": _plain(expected), "total": _plain(actual), "discounted_again": False},
        applied=True, status="match" if matched else "mismatch", reread=not matched,
        diagnosis=(diagnosis_extra + ("." if matched else ". 최종 합계와 다름")),
    )


def _tax(structure: dict) -> dict:
    if not _enabled("tax_composition"):
        return _result("tax_composition", rows=[], fields=[], evidence={}, applied=False, status="incomputable", diagnosis="규칙 꺼짐")
    supplies = [row for row in _adjustments(structure, "supply") if _known_amount(row) is not None]
    vats = [row for row in _adjustments(structure, "vat") if _known_amount(row) is not None]
    totals = [row for row in _adjustments(structure, "total") if _known_amount(row) is not None]
    if len(supplies) != 1 or len(vats) != 1 or len(totals) != 1:
        return _result("tax_composition", rows=[], fields=["supply", "vat", "total"], evidence={}, applied=False, status="incomputable", diagnosis="공급가액·부가세·최종 합계의 역할이 하나씩 확인되지 않음")
    supply = supplies[0]
    scope = supply.get("scope")
    exempts = _adjustments(structure, "exempt")
    services = _adjustments(structure, "service")
    if any(_known_amount(row) is None for row in exempts + services):
        return _result("tax_composition", rows=[], fields=["exempt", "service"], evidence={}, applied=False, status="incomputable", diagnosis="면세 또는 봉사료가 비어 있어 0으로 두지 않음")
    if scope == "all" and not exempts and not services:
        expected = _known_amount(supply) + _known_amount(vats[0])
    elif scope == "taxable" and exempts:
        expected = _known_amount(supply) + _known_amount(vats[0]) + sum((_known_amount(row) or Decimal("0")) for row in exempts + services)
    else:
        return _result(
            "tax_composition", rows=[supply["adjustment_id"]], fields=["scope"],
            evidence={"scope": scope, "exempt_rows": len(exempts)}, applied=False, status="incomputable",
            diagnosis="과세 공급가액과 전체 공급가액의 범위가 식에 맞지 않아 적용하지 않음",
        )
    actual = _known_amount(totals[0])
    matched = _close(expected, actual)
    return _result(
        "tax_composition", rows=[supply["adjustment_id"], vats[0]["adjustment_id"], totals[0]["adjustment_id"]],
        fields=["supply", "vat", "exempt", "service", "total"],
        evidence={"expected": _plain(expected), "total": _plain(actual), "scope": scope},
        applied=True, status="match" if matched else "mismatch", reread=not matched,
        diagnosis="세금 구성이 최종 합계와 같음" if matched else "세금 구성이 최종 합계와 다름",
    )


def _tender(structure: dict) -> list[dict]:
    if not _enabled("tender_composition"):
        return []
    results = []
    payments = [row for row in _adjustments(structure, "payment") if _known_amount(row) is not None]
    tendered = [row for row in _adjustments(structure, "tendered") if _known_amount(row) is not None]
    change = [row for row in _adjustments(structure, "change") if _known_amount(row) is not None]
    points = [row for row in _adjustments(structure, "points") if _known_amount(row) is not None]
    if len(payments) >= 2:
        # Several stated tenders are compared with each other only when one of
        # them is not also the sum. Without a separate charged total this is incomputable.
        results.append(_result(
            "tender_composition", rows=[row["adjustment_id"] for row in payments], fields=["payment"],
            evidence={"payments": [_plain(_known_amount(row)) for row in payments], "points_excluded": [_plain(_known_amount(row)) for row in points]},
            applied=False, status="incomputable",
            diagnosis="결제수단이 여러 개이나 청구액과 분리된 합계 역할이 없어 포인트·받은 돈을 더하지 않음",
        ))
    if len(tendered) == 1 and len(change) == 1 and len(payments) == 1:
        expected = _known_amount(tendered[0]) - _known_amount(change[0])
        actual = _known_amount(payments[0])
        matched = _close(expected, actual)
        results.append(_result(
            "tender_composition",
            rows=[tendered[0]["adjustment_id"], change[0]["adjustment_id"], payments[0]["adjustment_id"]],
            fields=["tendered", "change", "payment"],
            evidence={"expected": _plain(expected), "payment": _plain(actual)},
            applied=True, status="match" if matched else "mismatch", reread=not matched,
            diagnosis="받은 돈에서 거스름돈을 뺀 값이 결제액과 같음" if matched else "받은 돈과 거스름돈의 관계가 결제액과 다름. 음수·0원을 그 자체로 오류로 보지 않음",
        ))
    if not results:
        results.append(_result(
            "tender_composition", rows=[], fields=["payment", "tendered", "change", "points"],
            evidence={"payment_rows": len(payments), "point_rows": len(points)}, applied=False,
            status="incomputable", diagnosis="결제수단·받은 돈·거스름돈의 역할이 식을 적용할 만큼 확인되지 않음",
        ))
    return results


def _anomalies(structure: dict) -> list[dict]:
    if not _enabled("row_anomaly"):
        return []
    results = []
    seen: dict[tuple, str] = {}
    for row in structure.get("rows") or []:
        if row.get("row_type") != "item":
            continue
        quantity = parse_number(row.get("quantity"))
        unit = parse_number(row.get("unit_price"))
        amount = parse_number(row.get("line_amount"))
        if quantity is not None and unit is not None and amount is not None and not _close(quantity * unit, amount):
            swapped = _close(quantity * amount, unit) or _close(unit * amount, quantity)
            if swapped:
                results.append(_result(
                    "row_anomaly", rows=[row["row_id"]], fields=["quantity", "unit_price", "line_amount"],
                    evidence={"possible_column_shift": True}, applied=True, status="mismatch", reread=True,
                    diagnosis="숫자 열이 서로 바뀌었을 가능성이 있음. 인쇄값을 교환해 덮어쓰지 않음",
                ))
        key = (row.get("display_name"), _plain(amount))
        if row.get("display_name") and amount is not None and key in seen:
            results.append(_result(
                "row_anomaly", rows=[seen[key], row["row_id"]], fields=["raw_name", "line_amount"],
                evidence={"possible_duplicate": True}, applied=True, status="mismatch", reread=True,
                diagnosis="같은 이름과 같은 행 금액이 반복됨. 실제 반복 상품일 수 있어 삭제하지 않음",
            ))
        elif row.get("display_name") and amount is not None:
            seen[key] = row["row_id"]
        if amount is None and row.get("row_type") == "item":
            results.append(_result(
                "row_anomaly", rows=[row["row_id"]], fields=["line_amount"],
                evidence={"possible_missing_amount": True}, applied=True, status="mismatch", reread=True,
                diagnosis="상품 행에 행 금액이 없음",
            ))
    return results


def _plain(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")
