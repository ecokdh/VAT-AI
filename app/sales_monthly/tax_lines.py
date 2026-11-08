"""확인 저장한 월간 매출 정산서를 세액 계산·신고서용 매출 거래로 바꾼다(DB에 저장하지 않는다).

결제수단별 행 하나가 매출 거래 하나다. 과세 행에 공급가액이 인쇄되지 않았으면
합계금액을 공급대가로 보고 공급가액 = 합계금액 × 100/110(원 단위 반올림)으로 계산한다.
"""
import re
import uuid
from datetime import date

from sqlmodel import Session

from app.transactions.models import Transaction
from app.vat_return.engine import STANDARD_RATE

TAX_TREATMENT = {"과세": "standard", "면세": "exempt", "영세율": "zero"}
CARD_PAYMENTS = {"카드", "간편결제"}


def _evidence(row: dict) -> str:
    if "현금영수증" in (row.get("원문항목") or ""):
        return "cash_receipt"
    return "card_receipt" if row.get("결제수단") in CARD_PAYMENTS else "other"


def row_lines(document: dict) -> list[dict]:
    """금액이 있는 결제수단별 행마다 세액 계산에 넣을 값을 돌려준다."""
    lines = []
    for row in document.get("매출집계_유형별", []):
        total = row.get("합계금액")
        if not total:
            continue
        treatment = TAX_TREATMENT.get(row.get("과세구분"), "unknown")
        supply, vat, estimated = row.get("공급가액"), row.get("부가세"), False
        if treatment == "standard" and supply is None:
            supply, estimated = round(total * 10 / 11), True
        elif treatment in {"exempt", "zero"}:
            supply, vat = total if supply is None else supply, 0
        if vat is None and supply is not None:
            vat = total - supply
        lines.append({"name": row.get("원문항목") or "", "evidence_type": _evidence(row), "tax_treatment": treatment,
                      "total_amount": total, "supply_amount": supply, "vat_amount": vat, "supply_estimated": estimated})
    return lines


def summarize(document: dict) -> dict:
    """Legacy review preview only; no monthly settlement is reportable sales input."""
    lines = row_lines(document)
    return {"lines": [], "output_vat": None,
            "excluded_count": len(lines), "month_valid": sales_month(document) is not None,
            "reportable": False,
            "message": "POS 월정산은 세액 계산과 신고 매출에서 제외됩니다. 신고용 매출 집계에 홈택스 자료와 확인된 보완 매출을 연결해 주세요."}


def sales_month(document: dict) -> date | None:
    match = re.fullmatch(r"(\d{4})-(\d{2})", document.get("거래일") or "")
    if not match or not 1 <= int(match[2]) <= 12:
        return None
    return date(int(match[1]), int(match[2]), 1)


def period_sales(session: Session, user_id: uuid.UUID, start: date, end: date) -> list[Transaction]:
    """Deprecated compatibility hook: a POS monthly settlement is never reportable sales."""
    return []
