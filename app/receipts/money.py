"""영수증에 명시된 금액만으로 계산한다. 세율이나 미기재 면세액을 추측하지 않는다."""

from decimal import Decimal
import math


MONEY_FIELDS = (
    "amount", "supply_amount", "vat_amount", "taxable_supply_amount",
    "tax_exempt_amount", "transaction_amount", "payment_amount", "subtotal_amount",
)
PARTS = ("taxable_supply_amount", "tax_exempt_amount", "vat_amount")
NEW_FIELDS = ("taxable_supply_amount", "tax_exempt_amount", "transaction_amount", "payment_amount", "subtotal_amount")


def complete_money(values: dict, sources: dict, *, allow_signed: bool = False) -> tuple[dict, dict]:
    """입력 값을 덮지 않고, 분해식에서 유일하게 결정되는 누락 값만 보완한다."""
    values, sources = dict(values), dict(sources)

    def calculated(field: str, value: Decimal, rule: str) -> None:
        if sources.get(field, {}).get("state") in ("ABSENT", "FAILED", "NOT_APPLICABLE"):
            return
        if value.is_finite() and (value >= 0 or allow_signed) and math.isfinite(float(value)):
            values[field] = float(value)
            inputs = PARTS if rule == "sum_taxable_exempt_vat" else ("transaction_amount", "tax_exempt_amount") if rule == "transaction_equals_exempt" else ("transaction_amount", *(part for part in PARTS if part != field))
            sources[field] = {"kind": "calculated", "state": "READ", "rule": rule,
                "input_fields": list(inputs), "boxes": [box for key in inputs for box in sources.get(key, {}).get("boxes", [])], "confidence": None}

    total = values.get("transaction_amount")
    exempt = values.get("tax_exempt_amount")
    # 총액 전체가 명시된 면세액과 같을 때만 과세액·부가세 0을 보완한다.
    if total is not None and exempt is not None and total == exempt and (total > 0 or allow_signed and total < 0):
        for field in ("taxable_supply_amount", "vat_amount"):
            if values.get(field) is None:
                calculated(field, Decimal(0), "transaction_equals_exempt")

    if total is not None:
        missing = [field for field in PARTS if values.get(field) is None]
        if len(missing) == 1:
            remainder = Decimal(str(total)) - sum(
                (Decimal(str(values[field])) for field in PARTS if field != missing[0]),
                Decimal(0),
            )
            calculated(missing[0], remainder, "transaction_minus_other_parts")
    elif all(values.get(field) is not None for field in PARTS):
        calculated("transaction_amount", sum(
            (Decimal(str(values[field])) for field in PARTS), Decimal(0)
        ), "sum_taxable_exempt_vat")
    return values, sources


def structured_money(values: dict) -> bool:
    return any(values.get(field) is not None for field in NEW_FIELDS)


def money_problem(values: dict, *, required: bool = False) -> str | None:
    if not required and not structured_money(values):
        return None
    if any(values.get(field) is None for field in (*PARTS, "transaction_amount")):
        return "과세 공급가액·면세 금액·부가세·거래 총액을 확인하세요. 해당 없음은 0을 입력하세요."
    difference = sum((Decimal(str(values[field])) for field in PARTS), Decimal(0)) - Decimal(str(values["transaction_amount"]))
    if difference != 0:
        return "과세 공급가액·면세 금액·부가세의 합이 거래 총액과 다릅니다."
    return None


def complete_unit_price(row: dict) -> dict:
    """행 금액에 반영된 할인은 다시 빼지 않는다. 계산 단가는 행 금액/수량이다."""
    row = {**row, "sources": dict(row.get("sources") or {})}
    if row.get("unit_price") is not None:
        return row
    quantity, amount = row.get("quantity"), row.get("line_amount")
    if quantity is not None and amount is not None and math.isfinite(quantity) and math.isfinite(amount) and quantity > 0 and amount >= 0:
        unit = Decimal(str(amount)) / Decimal(str(quantity))
        if unit.is_finite() and math.isfinite(float(unit)):
            row["unit_price"] = float(unit)
            row["sources"]["unit_price"] = {"kind": "calculated", "rule": "line_amount_divided_by_quantity"}
    return row


def unit_price_problem(rows: list[dict]) -> str | None:
    if any(row.get("unit_price") is None for row in rows):
        return "단가를 보완하려면 품목 수량과 행 금액을 확인하세요."
    return None
