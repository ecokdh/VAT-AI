"""공제 판별 upsert와 기간별 리포트 집계. api-spec.md §3.3 참고."""

import re
import uuid
from datetime import date

from sqlmodel import Session, select

from app.common.exceptions import AppException
from app.deduction import ai_client
from app.deduction.models import Deduction
from app.deduction.schemas import DeductionOut, ReportItem, ReportOut
from app.receipts.models import Receipt


def analyze_receipt(session: Session, user_id: uuid.UUID, receipt_id: int) -> DeductionOut:
    statement = select(Receipt).where(Receipt.id == receipt_id, Receipt.user_id == user_id)
    receipt = session.exec(statement).first()

    if receipt is None:
        raise AppException(404, "NOT_FOUND", "영수증을 찾을 수 없습니다.")

    try:
        judgement = ai_client.judge_deduction(
            vendor=receipt.vendor or "",
            amount=receipt.amount or 0.0,
            ocr_raw=receipt.ocr_raw or "",
        )
    except AppException:
        raise
    except Exception as exc:
        raise AppException(502, "EXTERNAL_API_ERROR", "공제 판별 API 호출에 실패했습니다.") from exc

    deduction = session.exec(
        select(Deduction).where(Deduction.receipt_id == receipt.id)
    ).first()

    if deduction is None:
        deduction = Deduction(
            receipt_id=receipt.id,
            is_deductible=judgement.is_deductible,
            reason=judgement.reason,
            category=judgement.category,
            amount=judgement.amount,
        )
        session.add(deduction)
    else:
        deduction.is_deductible = judgement.is_deductible
        deduction.reason = judgement.reason
        deduction.category = judgement.category
        deduction.amount = judgement.amount

    session.commit()
    session.refresh(deduction)

    return DeductionOut(**deduction.model_dump())


def get_report(session: Session, user_id: uuid.UUID, period: str) -> ReportOut:
    start_date, end_date = _period_bounds(period)

    statement = (
        select(Receipt, Deduction)
        .join(Deduction, Deduction.receipt_id == Receipt.id)
        .where(
            Receipt.user_id == user_id,
            Receipt.date >= start_date,
            Receipt.date < end_date,
            Deduction.is_deductible.is_(True),
        )
    )

    rows = session.exec(statement).all()

    items = [
        ReportItem(
            receipt_id=receipt.id,
            vendor=receipt.vendor,
            amount=deduction.amount,
        )
        for receipt, deduction in rows
    ]

    return ReportOut(
        period=period,
        total_amount=sum(item.amount for item in items),
        count=len(items),
        items=items,
    )


def _period_bounds(period: str) -> tuple[date, date]:
    if not re.fullmatch(r"\d{4}-\d{2}", period):
        raise AppException(400, "VALIDATION_ERROR", "period는 YYYY-MM 형식이어야 합니다.")

    year, month = map(int, period.split("-"))

    if not 1 <= month <= 12:
        raise AppException(400, "VALIDATION_ERROR", "period는 YYYY-MM 형식이어야 합니다.")

    start_date = date(year, month, 1)
    end_date = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

    return start_date, end_date
