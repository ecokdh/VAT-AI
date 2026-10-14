from datetime import date, datetime, timedelta
import hashlib

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from app.auth import service as auth_service, password_reset
from app.auth.models import User, PasswordResetToken
from app.business.models import TaxProfileV2, BusinessProfile
from app.business.schemas import BusinessVerifyResponse
from app.core.config import settings
from app.core.database import get_session
from app.common.exceptions import AppException
from app.main import app
from app.jobs import service as jobs
from app.jobs.readiness import filing_readiness
from app.receipts.models import Receipt
from app.receipts.schemas import ExtractionConfirmation
from app.receipts.details import extract_details
from app.transactions.models import Transaction
from app.transactions.service import calculate_period_estimate


@pytest.fixture
def registration(monkeypatch):
    monkeypatch.setattr(auth_service, "verify_business", lambda _: BusinessVerifyResponse(
        business_number="1234567890", business_status="계속사업자", business_status_code="01",
        tax_type="일반과세자", tax_type_code="01", verified=True))
    return {"email": "qa4@example.com", "password": "Original-123!", "name": "QA",
            "business_name": "QA 상점", "business_number": "1234567890",
            "terms_accepted": True, "privacy_accepted": True}


@pytest.fixture
def mail(monkeypatch):
    delivered = []
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(settings, "SMTP_FROM", "reset@example.com")
    monkeypatch.setattr(password_reset, "send_reset_email", lambda email, token: delivered.append((email, token)))
    return delivered


def test_reset_is_one_time_and_revokes_previous_sessions(client, registration, mail):
    registered = client.post("/auth/register", json=registration).json()
    old_token = registered["access_token"]
    known = client.post("/auth/forgot-password", json={"email": registration["email"]})
    unknown = client.post("/auth/forgot-password", json={"email": "missing@example.com"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(mail) == 1
    token = mail[0][1]
    assert token not in str(known.json())
    session = next(app.dependency_overrides[get_session]())
    stored = session.exec(select(PasswordResetToken).where(PasswordResetToken.token_hash == hashlib.sha256(token.encode()).hexdigest())).one()
    assert stored.token_hash != token
    session.close()
    data = {"token": token, "password": "Changed-456!"}
    assert client.post("/auth/reset-password", json=data).status_code == 200
    assert client.post("/auth/reset-password", json=data).status_code == 400
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {old_token}"}).status_code == 401
    assert client.post("/auth/login", json={"email": registration["email"], "password": registration["password"]}).status_code == 401
    login = client.post("/auth/login", json={"email": registration["email"], "password": data["password"]})
    assert login.status_code == 200
    assert client.get("/auth/me", headers={"Authorization": f'Bearer {login.json()["access_token"]}'}).status_code == 200


def test_reset_expiry_throttling_and_missing_mail_config(client, registration, mail, monkeypatch):
    client.post("/auth/register", json=registration)
    for _ in range(5):
        assert client.post("/auth/forgot-password", json={"email": registration["email"]}).status_code == 202
    assert len(mail) == 3
    session = next(app.dependency_overrides[get_session]())
    for item in session.exec(select(PasswordResetToken)).all():
        item.expires_at = datetime.utcnow() - timedelta(minutes=1)
        session.add(item)
    session.commit()
    session.close()
    assert client.post("/auth/reset-password", json={"token": mail[-1][1], "password": "Changed-456!"}).status_code == 400
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    for email in (registration["email"], "missing@example.com"):
        response = client.post("/auth/forgot-password", json={"email": email})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "EMAIL_NOT_CONFIGURED"


def test_registration_saves_profile_atomically_and_remembers_guide(client, registration):
    profile = {"entity_type": "individual", "industry_category": "other", "business_start_date": "2025-01-01",
               "taxable_sales_h1": 0, "taxable_sales_h2": 0, "confirmed": True}
    response = client.post("/auth/register", json={**registration, "tax_profile": profile})
    assert response.status_code == 201
    headers = {"Authorization": f'Bearer {response.json()["access_token"]}'}
    assert client.get("/v2/business/tax-profile", headers=headers).json()["confirmed"] is True
    assert response.json()["user"]["ocr_guide_seen"] is False
    assert client.post("/auth/ocr-guide-seen", headers=headers).json()["ocr_guide_seen"] is True
    assert client.get("/auth/me", headers=headers).json()["ocr_guide_seen"] is True
    invalid = {**registration, "email": "invalid-profile@example.com", "tax_profile": {"confirmed": True}}
    assert client.post("/auth/register", json=invalid).status_code == 400
    assert client.post("/auth/email-availability", json={"email": invalid["email"]}).json()["available"] is True


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(email="db@example.com", name="QA", password_hash="unused")
        session.add(user); session.commit(); session.refresh(user)
        yield session, user
    engine.dispose()


def test_ocr_details_persist_without_confirming_transaction(db):
    session, user = db
    details = extract_details("사업자번호: 123-45-67890\n공급가액: 10,000\n부가세: 1,000\n승인번호: 987654\n상품: 원두")
    assert details["supply_amount"] == 10000 and details["vat_amount"] == 1000
    assert extract_details("합계: 11,000") == {}  # never infer VAT from the total
    receipt = Receipt(user_id=user.id, image_url="fixture.jpg", status="done", direction="sales")
    session.add(receipt); session.commit(); session.refresh(receipt)
    details["items"] = [{"name": "원두", "quantity": 2, "unit_price": 5000, "amount": 10000}]
    details["additional_fields"] = [{"label": "비고", "value": "테스트"}]
    result = jobs.confirm_receipt_extraction(session, user.id, receipt.id, ExtractionConfirmation(
        vendor="QA", amount=11000, date=date(2026, 9, 1), details=details))
    assert result.details["items"][0]["name"] == "원두"
    assert result.direction == "sales" and result.extraction_confirmed
    assert session.exec(select(Transaction)).all() == []


def test_pdf_checks_data_and_final_acknowledgement(db, monkeypatch):
    session, user = db
    estimate = {"period":"2026-H2", "status":"COMPLETE", "payable_estimate":1000}
    monkeypatch.setattr(jobs, "calculate_period_estimate", lambda *args: estimate)
    profile = TaxProfileV2(user_id=user.id, confirmed_at=datetime.utcnow())
    row = Transaction(user_id=user.id, direction="sales", transaction_date=date(2026,9,1), vendor="QA", total_amount=11000, state="draft")
    session.add_all([profile,row]); session.commit()
    with pytest.raises(AppException, match="모두 완료"):
        jobs.enqueue_pdf(session,user,"2026-H2",reviewed=True)
    row.state="confirmed"; session.add(row); session.commit()
    assert filing_readiness(session,user,"2026-H2",estimate)["ready"]
    with pytest.raises(AppException):
        jobs.enqueue_pdf(session,user,"2026-H2")
    assert jobs.enqueue_pdf(session,user,"2026-H2",reviewed=True).job_type == "pdf"
    session.add(Receipt(user_id=user.id,image_url="new.jpg",status="done",extraction_confirmed=True,date=date(2026,9,1)))
    session.commit()
    with pytest.raises(AppException):
        jobs.enqueue_pdf(session,user,"2026-H2",reviewed=True)


def test_2025_query_does_not_apply_2026_tax_rules(db):
    session,user=db
    session.add(BusinessProfile(user_id=user.id,business_number="1234567890",tax_type_code="01"))
    session.add(Transaction(user_id=user.id,direction="sales",transaction_date=date(2025,3,1),vendor="QA",total_amount=11000,state="confirmed"))
    session.commit()
    estimate=calculate_period_estimate(session,user,"2025-Q1",None)
    assert estimate["status"]=="UNAVAILABLE" and estimate["payable_estimate"] is None
    assert filing_readiness(session,user,"2025-Q1",estimate)["total"]==1
    assert filing_readiness(session,user,"2026-Q1",estimate)["total"]==0


def test_pdf_worker_uses_portable_renderer_without_wkhtmltopdf(db, monkeypatch):
    import json
    from types import SimpleNamespace
    import pdfkit
    from app.jobs.models import AsyncJob
    from app.jobs import worker

    session, user = db
    def missing_binary(**kwargs):
        raise OSError("wkhtmltopdf not installed")
    saved = []
    def capture_pdf(user_id, content, mime_type, extension):
        saved.append(content)
        assert user_id == user.id and mime_type == "application/pdf" and extension == "pdf"
        return SimpleNamespace(key="qa-only.pdf")
    monkeypatch.setattr(pdfkit, "configuration", missing_binary)
    monkeypatch.setattr(worker.receipt_service.storage, "save", capture_pdf)
    job = AsyncJob(user_id=user.id, job_type="pdf", payload_json=json.dumps({
        "period":"2026-H2", "output_vat":10000, "eligible_input_vat":2000,
        "deemed_input_vat":0, "payable_estimate":8000, "notes":["확정 거래 기준 <검토용>"]}))
    worker.process_async_job(session, job)
    assert saved[0].startswith(b"%PDF-") and b"%%EOF" in saved[0]
    assert json.loads(job.result_json)["file_key"] == "qa-only.pdf"
