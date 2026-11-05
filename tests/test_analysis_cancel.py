from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.deduction.analyzer import AnalysisDecision, LegalReference
from app.auth.models import User
from app.jobs import worker
from app.transactions import service
from app.transactions.models import AnalysisRun
from app.transactions.schemas import AnalysisRunCreate, TransactionCreate


DECISION = AnalysisDecision(
    disposition="DEDUCTIBLE",
    reason="업무용 소모품",
    legal_references=[LegalReference(source_id="VAT-ACT-38", title="부가가치세법 제38조")],
    analyzer_name="test-model",
    analyzer_version="test-1",
)


def setup_session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    user = User(email="cancel@example.com", password_hash="hash", name="owner")
    session.add(user)
    session.commit()
    session.refresh(user)
    return session, user


def confirmed_purchase(session, user, vendor="문구점"):
    item = service.create_transaction(session, user.id, TransactionCreate(
        direction="purchase", transaction_date=date(2026, 3, 2), vendor=vendor, description="업무용 소모품",
        evidence_type="tax_invoice", business_related=True, total_amount=1100, supply_amount=1000,
        vat_amount=100, tax_treatment="standard",
    ))
    return service.confirm_transaction(session, user.id, item.id)


def test_cancelled_pending_run_is_not_picked_up_by_worker():
    session, user = setup_session()
    item = confirmed_purchase(session, user)
    run = service.create_analysis_run(session, user.id, AnalysisRunCreate(transaction_ids=[item.id]))

    cancelled = service.cancel_analysis_run(session, user.id, run.id)

    assert cancelled.status == "CANCELLED"
    assert cancelled.finished_at is not None
    assert session.exec(select(AnalysisRun).where(AnalysisRun.status == "PENDING")).first() is None


def test_cancel_during_processing_discards_partial_results(monkeypatch):
    session, user = setup_session()
    first, second = confirmed_purchase(session, user), confirmed_purchase(session, user, "철물점")
    before = first.review_status
    run = service.create_analysis_run(session, user.id, AnalysisRunCreate(transaction_ids=[first.id, second.id]))

    class CancelOnFirstCall:
        def analyze(self, request):
            # 첫 거래를 분석하는 사이에 사용자가 화면에서 '예'를 눌러 중단한 상황.
            service.cancel_analysis_run(session, user.id, run.id)
            return DECISION

    monkeypatch.setattr(worker, "load_analyzer", lambda _: CancelOnFirstCall())
    with pytest.raises(worker.AnalysisCancelled):
        worker.process_analysis_run(session, run)
    session.rollback()

    session.refresh(run)
    session.refresh(first)
    assert run.status == "CANCELLED"
    assert run.result_json is None
    assert first.review_status == before


def test_cancel_after_completion_keeps_result():
    session, user = setup_session()
    item = confirmed_purchase(session, user)
    run = service.create_analysis_run(session, user.id, AnalysisRunCreate(transaction_ids=[item.id]))
    worker.process_analysis_run(session, run)
    session.commit()

    result = service.cancel_analysis_run(session, user.id, run.id)

    assert result.status == "COMPLETED"
    assert result.result_json is not None
