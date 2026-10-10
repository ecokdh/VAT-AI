from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.database import get_session
from app.transactions import service
from app.transactions.schemas import (
    AnalysisRunCreate,
    AnalysisRunOut,
    TaxEstimateOut,
    TransactionCreate,
    TransactionOut,
    TransactionUpdate,
)


router = APIRouter(prefix="/v2", tags=["transactions-v2"])


@router.post("/transactions", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_transaction(
    body: TransactionCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return service.create_transaction(session, user.id, body)


@router.post("/transactions/from-receipt/{receipt_id}", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_transaction_from_receipt(
    receipt_id: int,
    body: TransactionCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return service.create_from_receipt(session, user.id, receipt_id, body)


@router.get("/transactions", response_model=list[TransactionOut])
def list_transactions(
    direction: str | None = Query(default=None, pattern="^(purchase|sales)$"),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return service.list_transactions(session, user.id, direction)


@router.patch("/transactions/{transaction_id}", response_model=TransactionOut)
def update_transaction(
    transaction_id: int,
    body: TransactionUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return service.update_transaction(session, user.id, transaction_id, body)


@router.post("/transactions/{transaction_id}/confirm", response_model=TransactionOut)
def confirm_transaction(
    transaction_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return service.confirm_transaction(session, user.id, transaction_id)


@router.delete("/transactions/{transaction_id}", response_model=TransactionOut)
def move_to_trash(
    transaction_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return service.move_to_trash(session, user.id, transaction_id)


@router.get("/trash", response_model=list[TransactionOut])
def list_trash(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return service.list_trash(session, user.id)


@router.post("/trash/{transaction_id}/restore", response_model=TransactionOut)
def restore_transaction(
    transaction_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return service.restore_from_trash(session, user.id, transaction_id)


@router.post("/trash/{transaction_id}/permanent-delete-request", response_model=TransactionOut)
def request_permanent_delete(
    transaction_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return service.request_permanent_delete(session, user.id, transaction_id)


@router.post("/analysis-runs", response_model=AnalysisRunOut, status_code=status.HTTP_202_ACCEPTED)
def create_analysis_run(
    body: AnalysisRunCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return service.create_analysis_run(session, user.id, body)


@router.get("/analysis-runs/{run_id}", response_model=AnalysisRunOut)
def get_analysis_run(
    run_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return service.get_analysis_run(session, user.id, run_id)


@router.get("/tax-estimates/2026", response_model=TaxEstimateOut)
def get_tax_estimate(
    period: str,
    simplified_industry_rate: int | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return service.calculate_period_estimate(session, user, period, simplified_industry_rate)
