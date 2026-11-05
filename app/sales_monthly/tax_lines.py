"""확인 저장한 월간 매출 정산서를 세액 계산·신고서용 매출 거래로 바꾼다(DB에 저장하지 않는다).

결제수단별 행 하나가 매출 거래 하나다. 과세 행에 공급가액이 인쇄되지 않았으면
합계금액을 공급대가로 보고 공급가액 = 합계금액 × 100/110(원 단위 반올림)으로 계산한다.
"""
import json
import re
import uuid
from datetime import date

from sqlmodel import Session, select

from app.sales_monthly.models import MonthlySalesDocument
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
    """확인 화면용: 행별 반영값과 예상 매출세액(세액 계산과 같은 공급가액 × 10%), 빠진 행 수."""
    lines = row_lines(document)
    standard = [l for l in lines if l["tax_treatment"] == "standard"]
    return {"lines": lines, "output_vat": sum(l["supply_amount"] * STANDARD_RATE // 100 for l in standard),
            "excluded_count": sum(l["tax_treatment"] == "unknown" for l in lines),
            "month_valid": sales_month(document) is not None}


def sales_month(document: dict) -> date | None:
    match = re.fullmatch(r"(\d{4})-(\d{2})", document.get("거래일") or "")
    if not match or not 1 <= int(match[2]) <= 12:
        return None
    return date(int(match[1]), int(match[2]), 1)


def period_sales(session: Session, user_id: uuid.UUID, start: date, end: date) -> list[Transaction]:
    """기간 안의 확인 저장된 정산서를 확정 매출 거래 형태로 돌려준다."""
    docs = session.exec(select(MonthlySalesDocument).where(
        MonthlySalesDocument.user_id == user_id, MonthlySalesDocument.status == "reviewed",
        MonthlySalesDocument.deleted_at.is_(None))).all()
    rows = []
    for doc in docs:
        document = json.loads(doc.review_json)
        month = sales_month(document)
        if month is None or not start <= month < end:
            continue
        vendor = document["사업장"].get("상호") or "월간 매출 정산서"
        rows += [Transaction(user_id=user_id, direction="sales", state="confirmed", transaction_date=month,
                             vendor=vendor, description=line["name"], evidence_type=line["evidence_type"],
                             tax_treatment=line["tax_treatment"], total_amount=line["total_amount"],
                             supply_amount=line["supply_amount"], vat_amount=line["vat_amount"])
                 for line in row_lines(document)]
    return rows
