from datetime import datetime, timedelta
import smtplib
from uuid import UUID

import pytest
from sqlmodel import select

from app.auth import password_reset
from app.auth.models import PasswordResetToken
from app.core.config import settings
from app.core.database import get_session
from app.main import app
from test_qa4_flows import registration, mail  # noqa: F401


def request(client, registration):
    assert client.post("/auth/register", json=registration).status_code == 201
    response = client.post("/auth/forgot-password", json={"email": registration["email"].upper()})
    assert response.status_code == 202
    return response.json()["request_id"]


def edit_records(change):
    generator = app.dependency_overrides[get_session]()
    with next(generator) as session:
        for row in session.exec(select(PasswordResetToken)).all():
            change(row)
            session.add(row)
        session.commit()
    generator.close()


def test_returning_to_app_can_enter_already_sent_code_during_cooldown(client, registration, mail):
    rid = request(client, registration)
    # A request made outside this page must not strand the user at the email form.
    response = client.post("/auth/forgot-password", json={"email": registration["email"]})
    assert response.status_code == 202
    assert response.json()["request_id"] == rid
    assert len(mail) == 1
    assert 0 < response.json()["retry_after"] <= 60
    assert client.post("/auth/verify-reset-code", json={
        "request_id": rid, "code": mail[0][1],
    }).status_code == 200


def test_registered_recipients_share_sender_credentials_not_recipient_passwords(client, registration, mail, monkeypatch):
    monkeypatch.setattr(settings, "SMTP_USERNAME", "service-sender@example.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "sender-only-app-password")
    for email in ("new-owner@gmail.com", "another-owner@naver.com"):
        assert client.post("/auth/register", json={**registration, "email": email}).status_code == 201
        response = client.post("/auth/forgot-password", json={"email": email})
        assert response.status_code == 202
        assert mail[-1][0] == email
        assert settings.SMTP_USERNAME == "service-sender@example.com"
        assert settings.SMTP_PASSWORD == "sender-only-app-password"
        assert client.post("/auth/verify-reset-code", json={
            "request_id": response.json()["request_id"], "code": mail[-1][1],
        }).status_code == 200
    assert client.post("/auth/forgot-password", json={"email": "not-registered@gmail.com"}).status_code == 404
    assert len(mail) == 2


def test_code_attempt_limit_cannot_be_bypassed_with_correct_code(client, registration, mail):
    rid = request(client, registration)
    wrong = "000000" if mail[0][1] != "000000" else "111111"
    for _ in range(5):
        assert client.post("/auth/verify-reset-code", json={"request_id": rid, "code": wrong}).status_code == 400
    assert client.post("/auth/verify-reset-code", json={"request_id": rid, "code": mail[0][1]}).status_code == 400


def test_code_is_bound_to_request_and_single_use(client, registration, mail):
    rid = request(client, registration)
    assert client.post("/auth/verify-reset-code", json={"request_id": str(UUID(int=1)), "code": mail[0][1]}).status_code == 400
    data = {"request_id": rid, "code": mail[0][1]}
    assert client.post("/auth/verify-reset-code", json=data).status_code == 200
    assert client.post("/auth/verify-reset-code", json=data).status_code == 400


def test_unverified_code_cannot_reset_and_no_secrets_are_stored(client, registration, mail):
    rid = request(client, registration)
    generator = app.dependency_overrides[get_session]()
    with next(generator) as session:
        row = session.get(PasswordResetToken, UUID(rid))
        assert row.code_hash != mail[0][1]
        assert row.token_hash != mail[0][1]
        assert row.verified_at is None
    generator.close()
    assert client.post("/auth/reset-password", json={"token": mail[0][1], "password": "Changed-456!"}).status_code == 400


def test_resend_invalidates_previous_code_and_limits_hourly_requests(client, registration, mail):
    rid = request(client, registration)
    for _ in range(2):
        edit_records(lambda row: setattr(row, "created_at", row.created_at - timedelta(seconds=61)))
        response = client.post("/auth/forgot-password", json={"email": registration["email"]})
        assert response.status_code == 202
    assert len(mail) == 3
    assert client.post("/auth/verify-reset-code", json={"request_id": rid, "code": mail[0][1]}).status_code == 400
    assert client.post("/auth/forgot-password", json={"email": registration["email"]}).status_code == 202
    assert len(mail) == 3
    edit_records(lambda row: setattr(row, "created_at", row.created_at - timedelta(seconds=61)))
    assert client.post("/auth/forgot-password", json={"email": registration["email"]}).status_code == 429
    assert client.post("/auth/verify-reset-code", json={"request_id": response.json()["request_id"], "code": mail[-1][1]}).status_code == 200


def test_delivery_failure_is_reported_and_code_is_unusable(client, registration, mail, monkeypatch):
    client.post("/auth/register", json=registration)
    def fail(*_):
        raise smtplib.SMTPException("no delivery")
    monkeypatch.setattr(password_reset, "send_reset_email", fail)
    response = client.post("/auth/forgot-password", json={"email": registration["email"]})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "EMAIL_DELIVERY_FAILED"
    generator = app.dependency_overrides[get_session]()
    with next(generator) as session:
        row = session.exec(select(PasswordResetToken)).one()
        assert row.used_at is not None
    generator.close()


def test_verified_reset_token_expires_and_password_policy_is_enforced(client, registration, mail):
    rid = request(client, registration)
    token = client.post("/auth/verify-reset-code", json={"request_id": rid, "code": mail[0][1]}).json()["token"]
    for password in ("allletters", "12345678", "가" * 25 + "A1!"):
        assert client.post("/auth/reset-password", json={"token": token, "password": password}).status_code == 400
    edit_records(lambda row: setattr(row, "expires_at", datetime.utcnow() - timedelta(seconds=1)))
    assert client.post("/auth/reset-password", json={"token": token, "password": "Changed-456!"}).status_code == 400


@pytest.mark.parametrize("use_ssl", [False, True])
def test_smtp_mail_has_code_and_uses_tls(monkeypatch, use_ssl):
    sent, calls = [], []
    class SMTP:
        def __init__(self, host, port, **kwargs):
            calls.append((host, port, kwargs))
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def starttls(self, **_): calls.append("tls")
        def login(self, user, password): calls.append((user, password))
        def send_message(self, message): sent.append(message)
    monkeypatch.setattr(password_reset.smtplib, "SMTP_SSL" if use_ssl else "SMTP", SMTP)
    for key, value in {"SMTP_HOST": "smtp.example.com", "SMTP_PORT": 465 if use_ssl else 587,
                       "SMTP_FROM": "reset@example.com", "SMTP_USERNAME": "sender", "SMTP_PASSWORD": "secret",
                       "SMTP_USE_SSL": use_ssl}.items():
        monkeypatch.setattr(settings, key, value)
    password_reset.send_reset_email("owner@example.com", "012345")
    assert sent[0]["To"] == "owner@example.com"
    assert sent[0].get_content_type() == "multipart/alternative"
    plain = sent[0].get_body(preferencelist=("plain",))
    html = sent[0].get_body(preferencelist=("html",))
    assert plain is not None and html is not None
    for part in (plain, html):
        assert "012345" in part.get_content()
        assert "10분" in part.get_content()
    assert "VAT-AI" in sent[0]["From"]
    assert "VAT-AI 드림" in html.get_content()
    assert "<table" in html.get_content()
    assert ("tls" in calls) == (not use_ssl)
    assert ("sender", "secret") in calls


def test_email_template_escapes_dynamic_content():
    html = password_reset.render_reset_email_html('<img src="x" onerror="alert(1)">')
    assert '<img src="x"' not in html
    assert "&lt;img" in html
