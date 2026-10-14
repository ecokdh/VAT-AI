import json
from uuid import UUID
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
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
    direction: Literal["purchase", "sales"] = Form("purchase"),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    content = await file.read(settings.MAX_UPLOAD_SIZE_BYTES + 1)
    job, receipt = await service.enqueue_receipt_ocr(session, user.id, content, file.content_type, direction)
    return ReceiptJobAccepted(job_id=job.id, receipt_id=receipt.id, status="PENDING")


@router.get("/receipts/{receipt_id}/image")
def get_receipt_image(
    receipt_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    receipt = get_receipt_with_processing(receipt_id, user, session)
    try:
        content = receipt_service.storage.read(receipt.image_url)
    except OSError as exc:
        raise AppException(404, "NOT_FOUND", "원본 증빙을 찾을 수 없습니다.") from exc
    media_type = "image/png" if content.startswith(b"\x89PNG") else "image/jpeg"
    return Response(content=content, media_type=media_type, headers={"Cache-Control": "private, no-store"})


@router.post("/pdf-jobs", response_model=AsyncJobOut, status_code=202)
def create_pdf_job(
    period: str = Query(...),
    reviewed: bool = Query(False),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return service.enqueue_pdf(session, user, period, reviewed)


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


@router.post('/receipts/{receipt_id}/questions')
def receipt_questions(receipt_id:int,answers:dict[str,str],user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    from app.receipts.questions import questions,receipt_document,VERSION,canonical_answers,incomplete
    from app.business.models import TaxProfileV2
    receipt=session.exec(select(Receipt).where(Receipt.id==receipt_id,Receipt.user_id==user.id)).first()
    if receipt is None:raise AppException(404,'NOT_FOUND','영수증을 찾을 수 없습니다.')
    profile=session.exec(select(TaxProfileV2).where(TaxProfileV2.user_id==user.id)).first()
    doc=receipt_document(receipt)
    return {'version':VERSION,'answers':canonical_answers(doc,answers,receipt.direction),'questions':questions(doc,answers,receipt.direction,profile),'profile_complete':bool(profile and profile.onboarding_completed),'missing':incomplete(doc,answers,profile) if receipt.direction=='purchase' else []}
@router.get("/filing-readiness")
def get_filing_readiness(period: str, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    from app.jobs.readiness import filing_readiness
    from app.transactions.service import calculate_period_estimate
    try:
        estimate = calculate_period_estimate(session, user, period, None)
    except AppException as error:
        if error.code != "TAX_TYPE_UNAVAILABLE":
            raise
        estimate = {}
    return filing_readiness(session, user, period, estimate)
