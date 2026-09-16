"""이 라우터는 두 리소스를 함께 다룬다 (둘 다 Track C 소관, api-spec.md §3.3):
  - POST /receipts/{id}/analyze  (경로는 receipts 아래지만 공제 판별 로직은 여기)
  - GET  /reports?period=YYYY-MM
"""

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.database import get_session
from app.deduction import service
from app.deduction.schemas import DeductionOut, ReportOut

router = APIRouter(tags=["deduction"])


@router.post("/receipts/{receipt_id}/analyze", response_model=DeductionOut)
def analyze_receipt(
    receipt_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return service.analyze_receipt(session, user.id, receipt_id)


@router.get("/reports", response_model=ReportOut)
def get_report(
    period: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return service.get_report(session, user.id, period)
