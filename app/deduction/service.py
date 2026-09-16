"""Track C 구현 대상: 공제 판별 upsert + 기간별 리포트 집계. api-spec.md §3.3 참고."""

import uuid

from sqlmodel import Session

from app.deduction.schemas import DeductionOut, ReportOut


def analyze_receipt(session: Session, user_id: uuid.UUID, receipt_id: int) -> DeductionOut:
    raise NotImplementedError
    # TODO: receipt 조회(없으면 404) -> ai_client.judge_deduction() 호출
    # -> deductions upsert(receipt_id UNIQUE 기준 덮어쓰기) -> DeductionOut 반환


def get_report(session: Session, user_id: uuid.UUID, period: str) -> ReportOut:
    raise NotImplementedError
    # TODO: period="YYYY-MM" 파싱(형식 오류 시 400 VALIDATION_ERROR)
    # -> receipts.date가 해당 월 & deductions.is_deductible=true 인 건 합산
