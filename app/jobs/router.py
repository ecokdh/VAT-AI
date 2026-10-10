import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlmodel import Session, select

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.common.exceptions import AppException
from app.core.config import settings
from app.core.database import get_session
from app.jobs import service
from app.jobs.schemas import AsyncJobOut, ReceiptJobAccepted
from app.receipts import service as receipt_service
from app.receipts.storage import S3FileStorage
from app.receipts.models import Receipt
from app.receipts.schemas import ExtractionConfirmation, ReceiptProcessingOut, ReceiptRetryAccepted


router = APIRouter(prefix="/v2", tags=["async-jobs"])


@router.get("/receipts/{receipt_id}", response_model=ReceiptProcessingOut)
def get_receipt_with_processing(
    receipt_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    receipt = session.exec(select(Receipt).where(
        Receipt.id == receipt_id,
        Receipt.user_id == user.id,
    )).first()
    if receipt is None:
        raise AppException(404, "NOT_FOUND", "영수증을 찾을 수 없습니다.")
    return receipt


@router.get("/receipt-inbox", response_model=list[ReceiptProcessingOut])
def get_receipt_inbox(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return service.list_receipt_inbox(session, user.id)


@router.post("/receipts/{receipt_id}/confirm-extraction", response_model=ReceiptProcessingOut)
def confirm_receipt_extraction(
    receipt_id: int,
    payload: ExtractionConfirmation,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return service.confirm_receipt_extraction(session, user.id, receipt_id, payload)


@router.post("/receipts/{receipt_id}/retry", response_model=ReceiptRetryAccepted, status_code=202)
def retry_receipt_ocr(
    receipt_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    job, receipt = service.retry_receipt_ocr(session, user.id, receipt_id)
    return ReceiptRetryAccepted(receipt_id=receipt.id, job_id=job.id, status="PENDING", attempt=receipt.ocr_user_attempts)


@router.post("/receipt-jobs", response_model=ReceiptJobAccepted, status_code=202)
async def create_receipt_job(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    content = await file.read(settings.MAX_UPLOAD_SIZE_BYTES + 1)
    job, receipt = await service.enqueue_receipt_ocr(session, user.id, content, file.content_type)
    return ReceiptJobAccepted(job_id=job.id, receipt_id=receipt.id, status="PENDING")


@router.post("/pdf-jobs", response_model=AsyncJobOut, status_code=202)
def create_pdf_job(
    period: str = Query(...),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return service.enqueue_pdf(session, user, period)


@router.get("/jobs/{job_id}", response_model=AsyncJobOut)
def get_job(
    job_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return service.get_job(session, user.id, job_id)


@router.get("/pdf-jobs/{job_id}/download")
def download_pdf(
    job_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    job = service.get_job(session, user.id, job_id)
    if job.job_type != "pdf" or job.status != "COMPLETED" or not job.result_json:
        raise AppException(409, "PDF_NOT_READY", "PDF 작업이 아직 완료되지 않았습니다.")
    key = json.loads(job.result_json)["file_key"]
    storage = receipt_service.storage
    if isinstance(storage, S3FileStorage):
        return RedirectResponse(storage.presigned_url(key), status_code=307)
    return Response(
        content=storage.read(key),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="vat-ai-review-{job_id}.pdf"'},
    )
