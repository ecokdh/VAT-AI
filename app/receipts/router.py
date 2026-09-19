"""api-spec.md §3.2 — POST /receipts, GET /receipts, GET /receipts/{id}"""

from fastapi import APIRouter, Depends, File, UploadFile
from sqlmodel import Session

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.config import settings
from app.core.database import get_session
from app.receipts import service
from app.receipts.schemas import ReceiptOut, ReceiptSummary


router = APIRouter(prefix="/receipts", tags=["receipts"])


@router.post("", response_model=ReceiptOut, status_code=201)
async def upload_receipt(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ReceiptOut:
    # max+1만 읽어 큰 파일을 메모리에 전부 올리지 않고 크기 제한을 검사한다.
    file_bytes = await file.read(settings.MAX_UPLOAD_SIZE_BYTES + 1)
    return await service.upload_receipt(
        session, user.id, file_bytes, file.content_type
    )


@router.get("", response_model=list[ReceiptSummary])
def list_receipts(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[ReceiptSummary]:
    return service.list_receipts(session, user.id)


@router.get("/{receipt_id}", response_model=ReceiptOut)
def get_receipt(
    receipt_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ReceiptOut:
    return service.get_receipt(session, user.id, receipt_id)

