"""별지 제21호서식 1쪽에 넣을 값을 확정 거래에서 칸별로 모은다.

공제 여부는 세액 계산(tax_engine.calculate_estimate, 일반과세자)과 같은 기준으로 나누고,
신고서가 요구하는 칸 구분(증빙 종류·고정자산·불공제 세금계산서)만 더한다. 금액은 모두 코드가 계산한다.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.auth.models import User
from app.business.models import BusinessProfile, TaxProfileV2
from app.common.exceptions import AppException
from app.vat_return.engine import STANDARD_RATE, period_bounds
from app.transactions import service as transactions
from app.transactions.models import Transaction

KST = timezone(timedelta(hours=9))
CARD_EVIDENCE = {"card_receipt", "cash_receipt"}
PENDING_REVIEW = {"caution", "stale", "not_analyzed", "insufficient_info"}
ALWAYS_PRINTED = (9, 16, 18)  # 합계 칸은 0이어도 적는다.


def _deductible(row: Transaction) -> bool:
    # tax_engine 일반과세자 매입 공제 조건과 같다(standard 세율 + 분석 결과 SAFE).
    return (row.review_status == "analyzed" and row.risk_level == "SAFE" and row.business_related is not False
            and row.evidence_type != "unknown" and row.tax_treatment == "standard" and row.vat_amount is not None)


def _nondeductible_invoice(row: Transaction) -> bool:
    # 받은 세금계산서는 불공제분까지 (10)·(12)에 적고 (17)에서 뺀다.
    return (row.evidence_type == "tax_invoice" and row.tax_treatment == "standard" and row.vat_amount is not None
            and (row.review_status == "excluded" or row.business_related is False))


def _deemed_ready(row: Transaction) -> bool:
    return (row.review_status == "analyzed" and row.risk_level == "SAFE" and row.business_related is not False
            and row.tax_treatment == "exempt" and row.deemed_input_supply > 0
            and row.deemed_input_eligible is True and bool(row.deemed_input_document_type))


def _supply(row: Transaction) -> int:
    return row.supply_amount if row.supply_amount is not None else row.total_amount - (row.vat_amount or 0)


def _won(n: int) -> str:
    return f"-{-n:,}" if n < 0 else f"{n:,}"


def build_vat_return(session: Session, user: User, period: str) -> dict:
    """신고서 칸 값({필드 id: 인쇄 문자열})과 칸별 금액, 빈칸·제외 사유를 돌려준다."""
    estimate = transactions.calculate_period_estimate(session, user, period, None)
    if estimate["status"] == "UNAVAILABLE":
        raise AppException(409, "VAT_RETURN_UNAVAILABLE", estimate["notes"][0])
    if estimate["tax_type"] != "general":
        raise AppException(409, "VAT_RETURN_UNSUPPORTED", "간이과세자 신고서(별지 제44호서식)는 아직 지원하지 않습니다.")

    profile = session.exec(select(BusinessProfile).where(BusinessProfile.user_id == user.id)).first()
    tax_profile = session.exec(select(TaxProfileV2).where(TaxProfileV2.user_id == user.id)).first()
    start, end = period_bounds(period, "general")
    rows = transactions.period_transactions(session, user.id, start, end, tax_profile)

    r: dict = defaultdict(lambda: [0, 0])  # 줄 번호 → [금액, 세액]
    notes: list[str] = []
    skipped_sales = other_evidence = pending = deemed_supply = 0

    def add(row_no, amount: int, tax: int) -> None:
        r[row_no][0] += amount
        r[row_no][1] += tax

    for row in rows:
        if row.direction == "sales":
            if row.tax_treatment == "standard" and row.supply_amount is not None:
                line = 1 if row.evidence_type == "tax_invoice" else 3 if row.evidence_type in CARD_EVIDENCE else 4
                add(line, row.supply_amount, row.supply_amount * STANDARD_RATE // 100)
            elif row.tax_treatment == "zero" and row.supply_amount is not None:
                add(5 if row.evidence_type == "tax_invoice" else 6, row.supply_amount, 0)
            elif row.tax_treatment != "exempt":  # 면세 매출은 과세표준이 아니다.
                skipped_sales += 1
            continue
        if _deductible(row):
            if row.evidence_type == "tax_invoice":
                add(12 if row.is_fixed_asset else 10, _supply(row), row.vat_amount)
            elif row.evidence_type in CARD_EVIDENCE:
                add(15, _supply(row), row.vat_amount)
            else:
                other_evidence += 1
        elif _nondeductible_invoice(row):
            add(12 if row.is_fixed_asset else 10, _supply(row), row.vat_amount)
            add(17, _supply(row), row.vat_amount)
        elif _deemed_ready(row):
            deemed_supply += row.deemed_input_supply
        elif row.review_status in PENDING_REVIEW or row.risk_level == "CAUTION":
            pending += 1

    if estimate["deemed_input_vat"]:
        add(15, deemed_supply, estimate["deemed_input_vat"])

    r[9] = [sum(r[i][0] for i in range(1, 8)), sum(r[i][1] for i in range(1, 9))]
    r[16] = [r[10][0] - r[11][0] + sum(r[i][0] for i in range(12, 16)),
             r[10][1] - r[11][1] + sum(r[i][1] for i in range(12, 16))]
    r[18] = [r[16][0] - r[17][0], r[16][1] - r[17][1]]
    payable = r[9][1] - r[18][1]
    final = period.endswith(("H1", "H2"))
    filing = transactions.get_filing_input(session, user.id, period) if final else None
    if filing and filing.preliminary_notice_tax:
        r[24] = [0, filing.preliminary_notice_tax]
    total_due = payable - r[21][1] - sum(r[i][1] for i in range(22, 29)) + r[29][1]

    # 신고서 계산이 대시보드 예상세액과 어긋나면 알린다(정규 증빙이 아닌 공제 거래가 있으면 일부러 다르다).
    if r[9][1] != estimate["output_vat"]:
        notes.append("신고서 매출세액이 예상세액 계산과 다릅니다. 매출 거래의 과세 구분을 확인해 주세요.")
    if r[18][1] - estimate["deemed_input_vat"] != estimate["eligible_input_vat"] and not other_evidence:
        notes.append("신고서 매입세액이 예상세액 계산과 다릅니다. 매입 거래의 증빙 종류를 확인해 주세요.")
    if other_evidence:
        notes.append(f"세금계산서·카드·현금영수증이 아닌 증빙의 공제 거래 {other_evidence}건은 신고서 매입세액에 넣지 않았습니다.")
    if pending:
        notes.append(f"공제 여부를 아직 확인하지 않은 매입 {pending}건은 신고서에서 뺐습니다. 확인 후 다시 만들어 주세요.")
    if skipped_sales:
        notes.append(f"과세 구분이나 공급가액을 확인할 수 없는 매출 {skipped_sales}건은 신고서에서 뺐습니다.")
    notes.append("(20) 신용카드매출전표등 발행공제는 아직 계산하지 않아 빈칸입니다.")
    if final and not (filing and filing.preliminary_notice_tax is not None):
        notes.append("(24) 예정고지세액을 입력하지 않았습니다. 고지받은 세액이 있으면 신고서 생성 화면에서 입력해 주세요.")

    values: dict[str, str] = {}
    for row_no, (amount, tax) in sorted(r.items(), key=lambda kv: str(kv[0])):
        if amount or row_no in ALWAYS_PRINTED:
            values[f"r{row_no}.amount"] = _won(amount)
        if tax or row_no in ALWAYS_PRINTED:
            values[f"r{row_no}.tax"] = _won(tax)
    values["rda.tax"] = _won(payable)
    values["r30.tax"] = _won(total_due)

    last = end - timedelta(days=1)
    today = datetime.now(KST).date()
    reg_no = profile.business_number if profile else ""
    header = {
        "report.final" if final else "report.prelim": "V",
        "period.year": str(start.year), "period.term": "1" if start.month <= 6 else "2",
        "period.from_month": str(start.month), "period.from_day": str(start.day),
        "period.to_month": str(last.month), "period.to_day": str(last.day),
        "biz.name": profile.business_name if profile else None, "biz.owner": user.name,
        "biz.reg_no": f"{reg_no[:3]}-{reg_no[3:5]}-{reg_no[5:]}" if len(reg_no) == 10 else None,
        "biz.address": profile.business_address if profile else None,
        "base31.type": profile.business_type if profile else None,
        "base31.item": profile.business_item if profile else None,
        "base31.code": profile.industry_code if profile else None,
        "base31.amount": _won(r[9][0]), "base35.amount": _won(r[9][0]),
        "filed.year": str(today.year), "filed.month": str(today.month), "filed.day": str(today.day),
        "filed.signer": user.name,
    }
    values = {**{k: v for k, v in header.items() if v}, **values}
    return {"period": period, "values": values,
            "rows": {str(k): v for k, v in r.items() if v != [0, 0]}, "payable": total_due, "notes": notes}
