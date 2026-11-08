from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.database import get_session
from app.sales_filing import service
from app.sales_filing.schemas import FinalizeSalesCase, ManualSalesInput, SalesFeedback, SourceUpdate

router = APIRouter(prefix="/sales/filings", tags=["sales filing"])


@router.get("/{period}")
def get_sales_filing(period: str, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return service.public_result(service.refresh(session, user, period))


@router.put("/{period}/sources/{source}")
def update_source(
    period: str, source: str, body: SourceUpdate,
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
):
    case = service.update_source(
        session, user, period, source, status=body.status, query_start=body.query_start,
        query_end=body.query_end, basis=body.basis, document_ids=body.document_ids, reason=body.reason,
        expected_document_ids=body.expected_document_ids,
    )
    return service.public_result(case)


@router.post("/{period}/inputs")
def add_manual_input(
    period: str, body: ManualSalesInput,
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
):
    case = service.add_manual_input(session, user, period, body.model_dump(mode="json"))
    return service.public_result(case)


@router.post("/{period}/feedback")
def add_feedback(
    period: str, body: SalesFeedback,
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
):
    case = service.add_feedback(session, user, period, body.model_dump())
    return service.public_result(case)


@router.post("/{period}/validate")
def validate_sales_filing(period: str, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return service.public_result(service.refresh(session, user, period))


@router.post("/{period}/finalize")
def finalize_sales_filing(
    period: str, body: FinalizeSalesCase | None = None,
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
):
    return service.public_result(service.finalize(session, user, period, confirm_changed_sources=bool(body and body.confirm_changed_sources)))
