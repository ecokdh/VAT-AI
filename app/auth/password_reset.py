"""Single-use email password reset; plaintext tokens never enter API responses or logs."""
import hashlib
import hmac
import logging
import re
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta
from math import ceil
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from html import escape
from pathlib import Path
from string import Template
from uuid import UUID

from sqlalchemy import update
from sqlmodel import Session, select

from app.auth.models import PasswordResetToken, User
from app.common.exceptions import AppException
from app.core.config import settings
from app.core.security import hash_password


RESET_MESSAGE = "인증 코드를 이메일로 보냈습니다. 메일함과 스팸함을 확인해 주세요."
CODE_TTL_SECONDS = 600
RESEND_SECONDS = 60
MAX_CODE_ATTEMPTS = 5


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _code_digest(request_id: UUID, code: str) -> str:
    # A keyed digest protects the small code space if the database is exposed.
    return hmac.new(settings.JWT_SECRET.encode(), f"{request_id}:{code}".encode(), hashlib.sha256).hexdigest()


def render_reset_email_html(code: str) -> str:
    template = Path(__file__).with_name("templates") / "password_reset.html"
    return Template(template.read_text(encoding="utf-8")).substitute(code=escape(code))


def send_reset_email(email: str, code: str) -> None:
    message = EmailMessage()
    message["Subject"] = "VAT-AI 비밀번호 재설정 인증 코드"
    sender_name, sender_address = parseaddr(settings.SMTP_FROM)
    message["From"] = formataddr((sender_name or "VAT-AI", sender_address))
    message["To"] = email
    message.set_content(f"VAT-AI 비밀번호 재설정 인증 코드: {code}\n\n앱에서 위 6자리 코드를 10분 이내에 입력한 뒤 새 비밀번호를 설정해 주세요.\n코드는 다른 사람에게 알려주지 마세요.\n\n요청하지 않았다면 이 메일을 무시하셔도 됩니다. 비밀번호는 변경되지 않습니다.")
    message.add_alternative(render_reset_email_html(code), subtype="html")
    context = ssl.create_default_context()
    if settings.SMTP_USE_SSL:
        connection = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15, context=context)
    else:
        connection = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
    with connection as smtp:
        if not settings.SMTP_USE_SSL:
            smtp.starttls(context=context)
        if settings.SMTP_USERNAME:
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        smtp.send_message(message)


def request_reset(session: Session, email: str, client_ip: str) -> dict:
    normalized = email.strip().lower()
    now = datetime.utcnow()
    email_hash, ip_hash = _digest(normalized), _digest(client_ip)
    recent = session.exec(select(PasswordResetToken).where(
        PasswordResetToken.created_at > now - timedelta(hours=1),
        (PasswordResetToken.email_hash == email_hash) | (PasswordResetToken.ip_hash == ip_hash),
    )).all()
    user = session.exec(select(User).where(User.email == normalized)).first()
    if not user:
        raise AppException(404, "EMAIL_NOT_REGISTERED", "가입되지 않은 이메일입니다. 이메일을 확인하거나 회원가입해 주세요.")
    pending = sorted((row for row in recent if row.user_id == user.id), key=lambda row: row.created_at, reverse=True)
    latest = pending[0] if pending else None
    if latest and latest.created_at > now - timedelta(seconds=RESEND_SECONDS):
        if latest.code_hash and not latest.used_at and not latest.verified_at and latest.attempts < MAX_CODE_ATTEMPTS and latest.expires_at > now:
            # Resume code entry without sending again, e.g. after reloading the page.
            return {"message": "이미 인증 코드를 보냈습니다. 받은 메일의 코드를 입력해 주세요.",
                    "request_id": str(latest.id), "expires_in": ceil((latest.expires_at - now).total_seconds()),
                    "retry_after": ceil((latest.created_at + timedelta(seconds=RESEND_SECONDS) - now).total_seconds())}
        raise AppException(429, "RESET_RESEND_TOO_SOON", "인증 코드는 60초 후 다시 요청할 수 있습니다.")
    if sum(row.email_hash == email_hash for row in recent) >= 3 or sum(row.ip_hash == ip_hash for row in recent) >= 20:
        raise AppException(429, "RESET_RATE_LIMITED", "인증 코드 요청이 너무 많습니다. 1시간 후 다시 시도해 주세요.")
    if not settings.SMTP_HOST or not settings.SMTP_FROM:
        raise AppException(503, "EMAIL_NOT_CONFIGURED", "인증 메일을 보내지 못했습니다. 잠시 후 다시 시도해 주세요.")
    code = f"{secrets.randbelow(1_000_000):06d}"
    record = PasswordResetToken(user_id=user.id, token_hash=_digest(secrets.token_urlsafe(32)),
                                email_hash=email_hash, ip_hash=ip_hash, created_at=now,
                                expires_at=now + timedelta(seconds=CODE_TTL_SECONDS))
    record.code_hash = _code_digest(record.id, code)
    session.add(record)
    session.commit()
    try:
        send_reset_email(normalized, code)
    except (OSError, smtplib.SMTPException):
        logging.getLogger(__name__).error("Password reset email delivery failed; check SMTP configuration.")
        record.used_at = now
        session.add(record)
        session.commit()
        raise AppException(503, "EMAIL_DELIVERY_FAILED", "인증 메일을 보내지 못했습니다. 잠시 후 다시 시도해 주세요.") from None
    # Only invalidate previous codes after SMTP accepted the replacement email.
    session.execute(update(PasswordResetToken).where(
        PasswordResetToken.user_id == user.id, PasswordResetToken.id != record.id,
        PasswordResetToken.created_at <= record.created_at, PasswordResetToken.used_at.is_(None),
    ).values(used_at=now))
    session.commit()
    return {"message": RESET_MESSAGE, "request_id": str(record.id),
            "expires_in": CODE_TTL_SECONDS, "retry_after": RESEND_SECONDS}


def verify_reset_code(session: Session, request_id: UUID, code: str) -> dict:
    now = datetime.utcnow()
    # Reserve an attempt atomically, including wrong guesses and concurrent requests.
    attempted = session.execute(update(PasswordResetToken).where(
        PasswordResetToken.id == request_id, PasswordResetToken.code_hash.is_not(None),
        PasswordResetToken.used_at.is_(None), PasswordResetToken.verified_at.is_(None),
        PasswordResetToken.expires_at > now, PasswordResetToken.attempts < MAX_CODE_ATTEMPTS,
    ).values(attempts=PasswordResetToken.attempts + 1))
    if attempted.rowcount != 1:
        session.rollback()
        raise AppException(400, "INVALID_RESET_CODE", "인증 코드가 만료되었거나 사용할 수 없습니다. 새 코드를 요청해 주세요.")
    record = session.get(PasswordResetToken, request_id)
    if not record.user_id or not hmac.compare_digest(record.code_hash, _code_digest(request_id, code)):
        session.commit()
        raise AppException(400, "INVALID_RESET_CODE", "인증 코드가 올바르지 않습니다. 5회 오류 시 새 코드를 요청해 주세요.")
    token = secrets.token_urlsafe(32)
    record.token_hash = _digest(token)
    record.verified_at = now
    record.expires_at = now + timedelta(seconds=CODE_TTL_SECONDS)
    session.add(record)
    session.commit()
    return {"token": token, "message": "이메일 인증이 완료되었습니다. 새 비밀번호를 설정해 주세요."}


def reset_password(session: Session, token: str, password: str) -> dict:
    if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"[0-9]", password) or not re.search(r"[^A-Za-z0-9\s]", password):
        raise AppException(400, "WEAK_PASSWORD", "영문·숫자·특수문자를 포함한 8자 이상 비밀번호를 입력해 주세요.")
    hashed = hash_password(password)
    now = datetime.utcnow()
    record = session.exec(select(PasswordResetToken).where(PasswordResetToken.token_hash == _digest(token))).first()
    if not record or not record.user_id or record.used_at or record.expires_at <= now or (record.code_hash and not record.verified_at):
        raise AppException(400, "INVALID_RESET_TOKEN", "재설정 링크가 만료되었거나 유효하지 않습니다. 다시 요청해 주세요.")
    # Conditional consumption prevents two requests from using the same token concurrently.
    claimed = session.execute(update(PasswordResetToken).where(
        PasswordResetToken.id == record.id, PasswordResetToken.used_at.is_(None), PasswordResetToken.expires_at > now,
    ).values(used_at=now))
    if claimed.rowcount != 1:
        session.rollback()
        raise AppException(400, "INVALID_RESET_TOKEN", "이미 사용한 재설정 링크입니다.")
    session.execute(update(User).where(User.id == record.user_id).values(password_hash=hashed, token_version=User.token_version + 1))
    session.execute(update(PasswordResetToken).where(PasswordResetToken.user_id == record.user_id, PasswordResetToken.used_at.is_(None)).values(used_at=now))
    session.commit()
    return {"message": "비밀번호가 변경되었습니다. 새 비밀번호로 로그인해 주세요."}
