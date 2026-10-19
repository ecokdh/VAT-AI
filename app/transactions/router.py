from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session, select

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


@router.put('/transactions/{transaction_id}/question-answers',response_model=TransactionOut)
def update_question_answers(transaction_id:int,answers:dict[str,str],user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    from app.receipts.models import Receipt
    from app.business.models import TaxProfileV2
    from app.receipts.questions import validated_answers,receipt_document,facts,VERSION
    import json
    t=service._owned(session,user.id,transaction_id)
    receipt=session.get(Receipt,t.receipt_id) if t.receipt_id else None
    p=session.exec(select(TaxProfileV2).where(TaxProfileV2.user_id==user.id)).first()
    answers=validated_answers(receipt_document(receipt) if receipt else {},answers,t.direction,p)
    if json.loads(t.question_answers_json or '{}')==answers and t.question_rule_version==VERSION:
        return t
    old_summary=facts(json.loads(t.question_answers_json or '{}'))[1]
    t.question_answers_json=json.dumps(answers,ensure_ascii=False);t.question_rule_version=VERSION
    related,new_summary=facts(answers)
    t.business_related=related
    if not t.purpose or t.purpose==old_summary:t.purpose=new_summary
    t.review_status='stale';t.deductible_vat=0;t.risk_level=None;t.revision+=1
    t.analysis_reason='거래 목적이 변경되어 다시 분석해야 합니다.'
    t.legal_references_json='[]'
    t.updated_at=service._now()
    session.add(t);service._record_revision(session,t);session.commit();session.refresh(t);return t


@router.get('/transactions/{transaction_id}/questions')
def stored_questions(transaction_id:int,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    from app.receipts.models import Receipt
    from app.business.models import TaxProfileV2
    from app.receipts.questions import questions,receipt_document,VERSION,canonical_answers
    import json
    t=service._owned(session,user.id,transaction_id)
    receipt=session.get(Receipt,t.receipt_id) if t.receipt_id else None
    p=session.exec(select(TaxProfileV2).where(TaxProfileV2.user_id==user.id)).first()
    answers=json.loads(t.question_answers_json or '{}')
    return {'version':VERSION,'answers':canonical_answers(receipt_document(receipt) if receipt else {},answers,t.direction),'questions':questions(receipt_document(receipt) if receipt else {},answers,t.direction,p)}


@router.post('/transactions/{transaction_id}/questions')
def stored_question_preview(transaction_id:int,answers:dict[str,str],user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    from app.receipts.models import Receipt
    from app.business.models import TaxProfileV2
    from app.receipts.questions import questions,receipt_document,VERSION,canonical_answers
    t=service._owned(session,user.id,transaction_id)
    receipt=session.get(Receipt,t.receipt_id) if t.receipt_id else None
    p=session.exec(select(TaxProfileV2).where(TaxProfileV2.user_id==user.id)).first()
    return {'version':VERSION,'answers':canonical_answers(receipt_document(receipt) if receipt else {},answers,t.direction),'questions':questions(receipt_document(receipt) if receipt else {},answers,t.direction,p)}
