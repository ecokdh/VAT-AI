import uuid
from datetime import date

from sqlmodel import Session, SQLModel, create_engine, select

from app.auth.models import User
from app.common.exceptions import AppException
from app.business import service as business_service
from app.business.models import BusinessProfile, TaxProfileV2
from app.business.schemas import TaxProfileUpdate
from app.transactions import service
from app.transactions.models import AnalysisRun, Transaction, TransactionRevision
from app.transactions.schemas import AnalysisRunCreate, TransactionCreate, TransactionUpdate
from app.jobs.worker import process_analysis_run


def setup_session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    user = User(email="v2@example.com", password_hash="hash", name="owner")
    session.add(user)
    session.commit()
    session.refresh(user)
    return session, user


def purchase_data():
    return TransactionCreate(
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
    )


def test_edit_invalidates_purchase_analysis_and_estimate_immediately():
    session, user = setup_session()
    session.add(BusinessProfile(user_id=user.id, business_number="1234567890", tax_type_code="01"))
    session.commit()
    item = service.create_transaction(session, user.id, purchase_data())
    item = service.confirm_transaction(session, user.id, item.id)
    item.review_status = "analyzed"
    item.risk_level = "SAFE"
    item.deductible_vat = 100
    session.add(item)
    session.commit()

    updated = service.update_transaction(session, user.id, item.id, TransactionUpdate(vendor="다른 문구점"))
    estimate = service.calculate_period_estimate(session, user, "2026-H1", None)

    assert updated.review_status == "stale"
    assert updated.deductible_vat == 0
    assert estimate["eligible_input_vat"] == 0
    assert estimate["caution_transaction_count"] == 1


def test_trash_removes_transaction_and_restore_requires_reanalysis():
    session, user = setup_session()
    item = service.create_transaction(session, user.id, purchase_data())
    item = service.confirm_transaction(session, user.id, item.id)

    deleted = service.move_to_trash(session, user.id, item.id)
    assert deleted.state == "deleted"
    assert service.list_transactions(session, user.id) == []
    assert len(service.list_trash(session, user.id)) == 1

    restored = service.restore_from_trash(session, user.id, item.id)
    assert restored.state == "confirmed"
    assert restored.review_status == "stale"
    assert restored.deductible_vat == 0
    assert len(session.exec(select(TransactionRevision).where(TransactionRevision.transaction_id == item.id)).all()) == 4


def test_permanent_delete_request_respects_retention_state():
    session, user = setup_session()
    item = service.create_transaction(session, user.id, purchase_data())
    item = service.move_to_trash(session, user.id, item.id)
    try:
        service.request_permanent_delete(session, user.id, item.id)
        assert False, "unknown retention must be blocked"
    except AppException as error:
        assert error.code == "RETENTION_STATUS_UNCONFIRMED"

    item.retention_status = "required"
    session.add(item)
    session.commit()
    try:
        service.request_permanent_delete(session, user.id, item.id)
        assert False, "required records must be blocked"
    except AppException as error:
        assert error.code == "RETENTION_PERIOD_ACTIVE"

    item.retention_status = "not_required"
    session.add(item)
    session.commit()
    requested = service.request_permanent_delete(session, user.id, item.id)
    assert requested.permanent_delete_requested_at is not None


def test_worker_skips_run_when_selected_transaction_revision_changed():
    session, user = setup_session()
    item = service.create_transaction(session, user.id, purchase_data())
    item = service.confirm_transaction(session, user.id, item.id)
    run = service.create_analysis_run(session, user.id, AnalysisRunCreate(transaction_ids=[item.id]))
    item = service.update_transaction(session, user.id, item.id, TransactionUpdate(description="수정된 내용"))

    process_analysis_run(session, run)
    session.commit()
    session.refresh(run)
    session.refresh(item)
    assert run.status == "COMPLETED"
    assert '"status": "SKIPPED_STALE"' in run.result_json
    assert item.review_status == "stale"


def test_tax_type_change_inside_period_holds_estimate_for_manual_review():
    session, user = setup_session()
    session.add(BusinessProfile(user_id=user.id, business_number="1234567890", tax_type_code="01"))
    session.add(TaxProfileV2(
        user_id=user.id,
        tax_type_change_date=date(2026, 4, 1),
        changed_to_tax_type="simplified",
        confirmed_at=service._now(),
    ))
    session.commit()

    estimate = service.calculate_period_estimate(session, user, "2026-H1", None)

    assert estimate["status"] == "UNAVAILABLE"
    assert estimate["payable_estimate"] is None
    assert "과세기간 중 과세유형이 변경" in estimate["notes"][0]


def test_tax_profile_draft_can_be_saved_without_being_used_for_rates():
    session, user = setup_session()
    profile = business_service.save_tax_profile(session, user.id, TaxProfileUpdate(
        entity_type="individual",
        industry_category="food_service",
        taxable_sales_h1=100_000_000,
        confirmed=False,
    ))

    assert profile.entity_type == "individual"
    assert profile.confirmed_at is None
