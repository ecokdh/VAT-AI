"""api-spec.md §3.2 — GET /receipts, GET /receipts/{id}. 업로드는 POST /v2/receipt-jobs."""

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.database import get_session
from app.receipts import service
from app.receipts.schemas import ReceiptOut, ReceiptSummary


router = APIRouter(prefix="/receipts", tags=["receipts"])


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

