import json
import uuid
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.auth.models import User
from app.common.exceptions import AppException
from app.jobs.models import AsyncJob
from app.receipts import service as receipt_service
from app.receipts.models import Receipt
from app.receipts.schemas import ExtractionConfirmation
from app.transactions.models import Transaction
from app.transactions.service import calculate_period_estimate


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def enqueue_receipt_ocr(session: Session, user_id: uuid.UUID, content: bytes, content_type: str | None):
    media_type, extension = receipt_service.validate_image(content, content_type)
    try:
        stored = receipt_service.storage.save(user_id, content, media_type, extension)
    except OSError as exc:
        raise AppException(500, "STORAGE_ERROR", "파일 저장에 실패했습니다.") from exc
    initial_stages = {
        "photo_quality": "completed",
        "text_recognition": "processing",
        "transaction_extraction": "pending",
        "missing_field_check": "pending",
    }
    receipt = Receipt(
        user_id=user_id,
        image_url=stored.key,
        status="processing",
        processing_stage="text_recognition",
        processing_progress=20,
        stage_statuses_json=json.dumps(initial_stages),
    )
    commit_attempted = False
    try:
        session.add(receipt)
        session.flush()
        job = AsyncJob(
            user_id=user_id,
            job_type="ocr",
            payload_json=json.dumps({"receipt_id": receipt.id}, ensure_ascii=False),
        )
        session.add(job)
        commit_attempted = True
        session.commit()
    except Exception as exc:
        session.rollback()
        if not commit_attempted:
            try:
                receipt_service.storage.delete(stored.key)
            except Exception:
                pass
        raise AppException(500, "DATABASE_ERROR", "OCR 작업을 저장하지 못했습니다.") from exc
    session.refresh(receipt)
    session.refresh(job)
    return job, receipt


def enqueue_pdf(session: Session, user: User, period: str) -> AsyncJob:
    estimate = calculate_period_estimate(session, user, period, None)
    job = AsyncJob(
        user_id=user.id,
        job_type="pdf",
        payload_json=json.dumps(estimate, ensure_ascii=False),
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def get_job(session: Session, user_id: uuid.UUID, job_id: uuid.UUID) -> AsyncJob:
    job = session.exec(select(AsyncJob).where(AsyncJob.id == job_id, AsyncJob.user_id == user_id)).first()
    if job is None:
        raise AppException(404, "NOT_FOUND", "작업을 찾을 수 없습니다.")
    return job


def list_receipt_inbox(session: Session, user_id: uuid.UUID) -> list[Receipt]:
    """Extraction-confirmed OCR results that are not yet transaction records."""
    statement = (
        select(Receipt)
        .outerjoin(Transaction, Transaction.receipt_id == Receipt.id)
        .where(
            Receipt.user_id == user_id,
            Receipt.status == "done",
            Receipt.extraction_confirmed.is_(True),
            Transaction.id.is_(None),
        )
        .order_by(Receipt.created_at.desc(), Receipt.id.desc())
    )
    return list(session.exec(statement).all())


def confirm_receipt_extraction(
    session: Session, user_id: uuid.UUID, receipt_id: int, data: ExtractionConfirmation
) -> Receipt:
    receipt = session.exec(
        select(Receipt).where(Receipt.id == receipt_id, Receipt.user_id == user_id)
    ).first()
    if receipt is None:
        raise AppException(404, "NOT_FOUND", "영수증을 찾을 수 없습니다.")
    if receipt.status != "done":
        raise AppException(409, "OCR_NOT_COMPLETE", "OCR 완료 후 추출 결과를 확인해 주세요.")
    receipt.vendor = data.vendor.strip()
    receipt.amount = data.amount
    receipt.date = data.date
    receipt.extraction_confirmed = True
    receipt.ocr_missing_fields_json = "[]"
    session.add(receipt)
    session.commit()
    session.refresh(receipt)
    return receipt


def retry_receipt_ocr(session: Session, user_id: uuid.UUID, receipt_id: int):
    receipt = session.exec(
        select(Receipt).where(Receipt.id == receipt_id, Receipt.user_id == user_id)
    ).first()
    if receipt is None:
        raise AppException(404, "NOT_FOUND", "영수증을 찾을 수 없습니다.")
    if receipt.status != "failed":
        raise AppException(409, "OCR_RETRY_NOT_AVAILABLE", "실패한 OCR 작업만 다시 시도할 수 있습니다.")
    if receipt.ocr_user_attempts >= 2:
        raise AppException(409, "OCR_RETRY_LIMIT", "같은 사진으로 재시도할 수 있는 횟수를 모두 사용했습니다.")
    receipt.ocr_user_attempts += 1
    receipt.status = "processing"
    receipt.processing_stage = "text_recognition"
    receipt.processing_progress = 20
    receipt.stage_statuses_json = json.dumps({
        "photo_quality": "completed", "text_recognition": "processing",
        "transaction_extraction": "pending", "missing_field_check": "pending",
    })
    receipt.ocr_warnings_json = "[]"
    receipt.ocr_missing_fields_json = "[]"
    job = AsyncJob(
        user_id=user_id,
        job_type="ocr",
        payload_json=json.dumps({"receipt_id": receipt.id}, ensure_ascii=False),
    )
    session.add(receipt)
    session.add(job)
    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        raise AppException(500, "DATABASE_ERROR", "OCR 재시도 작업을 저장하지 못했습니다.") from exc
    session.refresh(job)
    return job, receipt
