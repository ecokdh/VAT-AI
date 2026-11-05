from datetime import date

import pytest
from pydantic import ValidationError
from sqlmodel import Session, SQLModel, create_engine

from app.auth.models import User
from app.business.models import BusinessProfile
from app.business.router import save_filing_info
from app.business.schemas import BusinessFilingInfo
from app.common.exceptions import AppException
from app.transactions import service
from app.transactions.schemas import TransactionCreate


def setup_session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    user = User(email="filing@example.com", password_hash="hash", name="owner")
    session.add(user)
    session.commit()
    session.refresh(user)
    return session, user


def purchase(session, user, direction="purchase"):
    item = service.create_transaction(session, user.id, TransactionCreate(
        direction=direction, transaction_date=date(2026, 3, 25), vendor="주방기기상사", description="업소용 그라인더",
        evidence_type="tax_invoice", business_related=True, total_amount=550000, supply_amount=500000,
        vat_amount=50000, tax_treatment="standard",
    ))
    return service.confirm_transaction(session, user.id, item.id)


def test_fixed_asset_flag_keeps_revision_and_analysis():
    session, user = setup_session()
    item = purchase(session, user)
    item.review_status, item.risk_level = "analyzed", "SAFE"
    session.add(item)
    session.commit()
    revision = item.revision

    updated = service.set_fixed_asset(session, user.id, item.id, True)

    assert updated.is_fixed_asset is True
    assert updated.revision == revision
    assert (updated.review_status, updated.risk_level) == ("analyzed", "SAFE")


def test_fixed_asset_flag_is_purchase_only():
    session, user = setup_session()
    sale = purchase(session, user, direction="sales")
    with pytest.raises(AppException):
        service.set_fixed_asset(session, user.id, sale.id, True)


def test_preliminary_notice_tax_is_saved_per_final_period():
    session, user = setup_session()
    service.save_filing_input(session, user.id, "2026-H1", 1_200_000)
    service.save_filing_input(session, user.id, "2026-H1", 900_000)

    assert service.get_filing_input(session, user.id, "2026-H1").preliminary_notice_tax == 900_000
    assert service.get_filing_input(session, user.id, "2026-H2") is None
    with pytest.raises(AppException):
        service.save_filing_input(session, user.id, "2026-Q1", 100)


def test_filing_info_blank_values_become_empty_and_code_must_be_six_digits():
    info = BusinessFilingInfo(business_address="  서울특별시 마포구 월드컵로 1 ", business_type="", industry_code="552202")
    assert info.business_address == "서울특별시 마포구 월드컵로 1"
    assert info.business_type is None
    with pytest.raises(ValidationError):
        BusinessFilingInfo(industry_code="55-22")


def test_saving_filing_info_does_not_reset_purchase_analysis():
    session, user = setup_session()
    session.add(BusinessProfile(user_id=user.id, business_number="1234567890", business_name="카페"))
    item = purchase(session, user)
    item.review_status = "analyzed"
    session.add(item)
    session.commit()

    result = save_filing_info(BusinessFilingInfo(business_address="부산광역시 수영구 1", business_type="음식점업",
                                                 business_item="커피", industry_code="552202"), user, session)

    session.refresh(item)
    assert (result["business_type"], result["industry_code"]) == ("음식점업", "552202")
    assert item.review_status == "analyzed"
