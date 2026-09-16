"""Track B 구현 대상: 업로드+OCR, 목록/상세 조회. api-spec.md §3.2 참고."""

import uuid

from sqlmodel import Session

from app.receipts.schemas import ReceiptOut, ReceiptSummary


def upload_receipt(session: Session, user_id: uuid.UUID, file_bytes: bytes, content_type: str) -> ReceiptOut:
    raise NotImplementedError
    # TODO: S3/로컬 저장 -> ocr_client.extract_receipt() 동기 호출
    # -> 성공: status="done" + 추출 필드 채움 / 실패: status="failed" + 필드 전부 None
    # -> Receipt 저장 후 ReceiptOut 반환 (항상 201, 실패도 status 필드로만 구분)


def list_receipts(session: Session, user_id: uuid.UUID) -> list[ReceiptSummary]:
    raise NotImplementedError  # TODO: user_id 소유, created_at DESC


def get_receipt(session: Session, user_id: uuid.UUID, receipt_id: int) -> ReceiptOut:
    raise NotImplementedError  # TODO: 없거나 타인 소유면 AppError(404, "NOT_FOUND", ...)
