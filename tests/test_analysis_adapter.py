from datetime import date

import pytest
from pydantic import ValidationError

from app.auth.models import User
from app.business.models import BusinessProfile
from app.analysis.contract import AnalysisDecision, LegalReference
from app.transactions import service
from app.transactions.models import AnalysisRun
from app.transactions.schemas import AnalysisRunCreate, TransactionCreate
from app.jobs import worker


class FixedAnalyzer:
    def __init__(self, decision: AnalysisDecision):
        self.decision = decision

    def analyze(self, request):
        assert request.contract_version == "v1"
        assert request.transaction.vendor == "문구점"
        return self.decision


def setup_session():
    from sqlmodel import Session, SQLModel, create_engine

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    user = User(email="adapter@example.com", password_hash="hash", name="owner")
    session.add(user)
    session.commit()
    session.refresh(user)
    session.add(BusinessProfile(user_id=user.id, business_number="1234567890", tax_type_code="01"))
    session.commit()
    return session, user


def create_confirmed_purchase(session, user):
    item = service.create_transaction(session, user.id, TransactionCreate(
        direction="purchase",
        transaction_date=date(2026, 3, 2),
        vendor="문구점",
        description="업무용 소모품",
        evidence_type="tax_invoice",
        business_related=True,
        total_amount=1100,
        supply_amount=1000,
        vat_amount=100,
        tax_treatment="standard",
    ))
    return service.confirm_transaction(session, user.id, item.id)


@pytest.mark.parametrize(
    ("disposition", "review_status", "risk_level", "expected_input_vat", "expected_uncalculated"),
    [
        ("DEDUCTIBLE", "analyzed", "SAFE", 100, 0),
        ("NOT_DEDUCTIBLE", "excluded", "NOT_DEDUCTIBLE", 0, 0),
        ("INSUFFICIENT_INFO", "insufficient_info", "CAUTION", 0, 1),
    ],
)
def test_adapter_decision_maps_to_tax_engine_without_model_amounts(
    monkeypatch, disposition, review_status, risk_level, expected_input_vat, expected_uncalculated
):
    session, user = setup_session()
    item = create_confirmed_purchase(session, user)
    run = service.create_analysis_run(session, user.id, AnalysisRunCreate(transaction_ids=[item.id]))
    decision = AnalysisDecision(
        disposition=disposition,
        reason="검토 결과",
        legal_references=[LegalReference(source_id="VAT-ACT-17", title="부가가치세법 제17조")]
        if disposition in {"DEDUCTIBLE", "NOT_DEDUCTIBLE"} else [],
        analyzer_name="test-model",
        analyzer_version="test-1",
        knowledge_version="test-law-2026",
    )
    monkeypatch.setattr(worker, "load_analyzer", lambda _: FixedAnalyzer(decision))

    worker.process_analysis_run(session, run)
    session.commit()
    session.refresh(item)
    assert item.review_status == review_status
    assert item.risk_level == risk_level
    assert item.deductible_vat == 0
    estimate = service.calculate_period_estimate(session, user, "2026-H1", None)
    assert estimate["eligible_input_vat"] == expected_input_vat
    assert estimate["uncalculated_transaction_count"] == expected_uncalculated
    session.close()


def test_final_model_decision_without_legal_reference_is_held_for_review(monkeypatch):
    session, user = setup_session()
    item = create_confirmed_purchase(session, user)
    run = service.create_analysis_run(session, user.id, AnalysisRunCreate(transaction_ids=[item.id]))
    decision = AnalysisDecision(
        disposition="DEDUCTIBLE",
        reason="분류 결과",
        analyzer_name="test-model",
        analyzer_version="test-1",
    )
    monkeypatch.setattr(worker, "load_analyzer", lambda _: FixedAnalyzer(decision))

    worker.process_analysis_run(session, run)
    session.commit()
    session.refresh(item)
    assert item.review_status == "caution"
    assert item.deductible_vat == 0
    session.close()


def test_analysis_contract_rejects_model_calculated_amounts():
    with pytest.raises(ValidationError):
        AnalysisDecision.model_validate({
            "disposition": "DEDUCTIBLE",
            "reason": "결정",
            "analyzer_name": "model",
            "analyzer_version": "1",
            "deductible_amount": 100,
        })
