"""api-spec.md §3.2 — POST /receipts, GET /receipts, GET /receipts/{id}"""

from fastapi import APIRouter, Depends, UploadFile
from sqlmodel import Session

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.database import get_session
from app.receipts import service
from app.receipts.schemas import ReceiptOut, ReceiptSummary

router = APIRouter(prefix="/receipts", tags=["receipts"])


@router.post("", response_model=ReceiptOut, status_code=201)
async def upload_receipt(
    file: UploadFile,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    file_bytes = await file.read()
    return service.upload_receipt(session, user.id, file_bytes, file.content_type)


@router.get("", response_model=list[ReceiptSummary])
def list_receipts(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return service.list_receipts(session, user.id)


@router.get("/{receipt_id}", response_model=ReceiptOut)
def get_receipt(
    receipt_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return service.get_receipt(session, user.id, receipt_id)
