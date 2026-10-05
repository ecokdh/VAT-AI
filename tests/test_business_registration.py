import pytest
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from app.auth import service as auth_service
from app.auth.models import User
from app.business.models import BusinessProfile
from app.business import nts_client
from app.business.schemas import BusinessVerifyResponse
from app.common.exceptions import AppException
from app.core.database import get_session
from app.deduction.models import Deduction
from app.main import app
from app.receipts.models import Receipt


def body(email="owner@example.com"):
    return {
        "email": email, "password": "correct-password", "name": "Owner",
        "business_name": " Owner Store ", "business_number": "123-45-67890",
    }


def mock_status(monkeypatch, code="01", status="계속사업자"):
    def verify(number):
        assert number == "123-45-67890"
        return BusinessVerifyResponse(
            business_number="1234567890", business_status=status,
            business_status_code=code, tax_type="부가가치세 일반과세자",
            tax_type_code="01", end_date="20200101" if code == "03" else None,
            verified=True,
        )
    monkeypatch.setattr(auth_service, "verify_business", verify)


def db_rows(model):
    generator = app.dependency_overrides[get_session]()
    session = next(generator)
    try:
        return session.exec(select(model)).all()
    finally:
        generator.close()


@pytest.mark.parametrize("code,status", [("01", "계속사업자"), ("02", "휴업자"), ("03", "폐업자")])
def test_registration_persists_user_and_business(client, monkeypatch, code, status):
    mock_status(monkeypatch, code, status)
    registered = client.post("/auth/register", json=body())
    assert registered.status_code == 201
    token = registered.json()["access_token"]
    users = db_rows(User)
    profiles = db_rows(BusinessProfile)
    assert len(users) == len(profiles) == 1
    assert profiles[0].user_id == users[0].id
    assert profiles[0].business_name == "Owner Store"
    assert profiles[0].business_number == "1234567890"
    assert profiles[0].business_status == status
    assert profiles[0].business_status_code == code
    assert profiles[0].verification_status == "status_checked"
    assert profiles[0].verified_at is not None
    assert profiles[0].end_date == ("20200101" if code == "03" else None)
    assert users[0].name == "Owner"

    login = client.post("/auth/login", json={"email": "owner@example.com", "password": "correct-password"})
    assert login.status_code == 200
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    business = me.json()["business"]
    assert business["business_status"] == status
    assert business["tax_type"] == "부가가치세 일반과세자"
    assert business["verification_status"] == "status_checked"
    assert business["verified_at"] is not None
    assert business["business_name"] == "Owner Store"
    assert "password_hash" not in registered.text + login.text + me.text
    assert db_rows(Deduction) == []


@pytest.mark.parametrize("code,http_status", [("BUSINESS_NOT_REGISTERED", 404), ("BUSINESS_API_TIMEOUT", 504)])
def test_lookup_failure_does_not_register(client, monkeypatch, code, http_status):
    def fail(_):
        raise AppException(http_status, code, "조회 실패")
    monkeypatch.setattr(auth_service, "verify_business", fail)
    result = client.post("/auth/register", json=body())
    assert result.status_code == http_status
    assert result.json()["error"]["code"] == code
    assert db_rows(User) == []
    assert db_rows(BusinessProfile) == []


def test_duplicate_email_does_not_repeat_lookup(client, monkeypatch):
    mock_status(monkeypatch)
    assert client.post("/auth/register", json=body()).status_code == 201

    def unexpected(_):
        pytest.fail("Duplicate email must be rejected before NTS lookup")
    monkeypatch.setattr(auth_service, "verify_business", unexpected)
    result = client.post("/auth/register", json=body())
    assert result.status_code == 409
    assert len(db_rows(User)) == len(db_rows(BusinessProfile)) == 1


def test_business_insert_failure_rolls_back_user(client, monkeypatch):
    mock_status(monkeypatch)

    def fail_insert(*_):
        raise SQLAlchemyError("profile insert failed")

    event.listen(BusinessProfile, "before_insert", fail_insert)
    try:
        result = client.post("/auth/register", json=body())
    finally:
        event.remove(BusinessProfile, "before_insert", fail_insert)
    assert result.status_code == 500
    assert result.json()["error"]["code"] == "DATABASE_ERROR"
    assert db_rows(User) == []
    assert db_rows(BusinessProfile) == []


def test_registration_normalizes_number_before_lookup(client, monkeypatch):
    def lookup(number):
        assert number == "1234567890"
        return {
            "b_no": number, "b_stt": "계속사업자", "b_stt_cd": "01",
            "tax_type": "부가가치세 일반과세자", "tax_type_cd": "01", "end_dt": "",
        }
    monkeypatch.setattr(nts_client, "lookup_status", lookup)
    assert client.post("/auth/register", json=body()).status_code == 201
    assert db_rows(BusinessProfile)[0].business_number == "1234567890"


def test_unconfirmed_lookup_does_not_register(client, monkeypatch):
    monkeypatch.setattr(auth_service, "verify_business", lambda _: BusinessVerifyResponse(
        business_number="1234567890", business_status="계속사업자",
        business_status_code="01", tax_type="부가가치세 일반과세자",
        tax_type_code="01", verified=False,
    ))
    result = client.post("/auth/register", json=body())
    assert result.status_code == 502
    assert db_rows(User) == []


def test_closed_business_registration_does_not_change_existing_deduction(client, monkeypatch):
    generator = app.dependency_overrides[get_session]()
    session = next(generator)
    try:
        other = User(email="other@example.com", password_hash="unused", name="Other")
        session.add(other)
        session.flush()
        receipt = Receipt(user_id=other.id, image_url="test.jpg", status="done")
        session.add(receipt)
        session.flush()
        session.add(Deduction(receipt_id=receipt.id, is_deductible=False, reason="existing", category="test", amount=0))
        session.commit()
    finally:
        generator.close()

    mock_status(monkeypatch, "03", "폐업자")
    assert client.post("/auth/register", json=body()).status_code == 201
    deductions = db_rows(Deduction)
    assert len(deductions) == 1
    assert deductions[0].is_deductible is False
    assert deductions[0].reason == "existing"
