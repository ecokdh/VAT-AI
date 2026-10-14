"""Single-use email password reset; plaintext tokens never enter API responses or logs."""
import hashlib
import logging
import re
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage

from sqlalchemy import update
from sqlmodel import Session, select

from app.auth.models import PasswordResetToken, User
from app.common.exceptions import AppException
from app.core.config import settings
from app.core.security import hash_password


RESET_MESSAGE = "가입된 이메일이면 비밀번호 재설정 안내를 보냈습니다. 메일함과 스팸함을 확인해 주세요."


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def send_reset_email(email: str, token: str) -> None:
    message = EmailMessage()
    message["Subject"] = "VAT-AI 비밀번호 재설정"
    message["From"] = settings.SMTP_FROM
    message["To"] = email
    link = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password#token={token}"
    message.set_content(f"아래 링크에서 20분 이내에 새 비밀번호를 설정해 주세요.\n\n{link}\n\n요청하지 않았다면 이 메일을 무시하셔도 됩니다.")
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
    if not settings.SMTP_HOST or not settings.SMTP_FROM:
        raise AppException(503, "EMAIL_NOT_CONFIGURED", "비밀번호 재설정 메일 서비스 준비 중입니다. 관리자에게 문의해 주세요.")
    normalized = email.strip().lower()
    now = datetime.utcnow()
    email_hash, ip_hash = _digest(normalized), _digest(client_ip)
    recent = session.exec(select(PasswordResetToken).where(
        PasswordResetToken.created_at > now - timedelta(hours=1),
        (PasswordResetToken.email_hash == email_hash) | (PasswordResetToken.ip_hash == ip_hash),
    )).all()
    if sum(row.email_hash == email_hash for row in recent) >= 3 or sum(row.ip_hash == ip_hash for row in recent) >= 20:
        # Same response for registered and unregistered addresses, including throttled requests.
        return {"message": RESET_MESSAGE}
    user = session.exec(select(User).where(User.email == normalized)).first()
    token = secrets.token_urlsafe(32)
    record = PasswordResetToken(user_id=user.id if user else None, token_hash=_digest(token),
                                email_hash=email_hash, ip_hash=ip_hash, created_at=now,
                                expires_at=now + timedelta(minutes=20))
    session.add(record)
    session.commit()
    if user:
        try:
            send_reset_email(normalized, token)
        except (OSError, smtplib.SMTPException):
            logging.getLogger(__name__).error("Password reset email delivery failed; check SMTP configuration.")
            # Do not disclose account existence through delivery failures.
            record.used_at = now
            session.add(record)
            session.commit()
    return {"message": RESET_MESSAGE}


def reset_password(session: Session, token: str, password: str) -> dict:
    if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"[0-9]", password) or not re.search(r"[^A-Za-z0-9\s]", password):
        raise AppException(400, "WEAK_PASSWORD", "영문·숫자·특수문자를 포함한 8자 이상 비밀번호를 입력해 주세요.")
    hashed = hash_password(password)
    now = datetime.utcnow()
    record = session.exec(select(PasswordResetToken).where(PasswordResetToken.token_hash == _digest(token))).first()
    if not record or not record.user_id or record.used_at or record.expires_at <= now:
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
