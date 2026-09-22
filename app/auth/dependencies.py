"""다른 트랙(receipts, deduction)이 재사용하는 JWT 사용자 의존성."""

import uuid

from fastapi import Depends, Header
from sqlmodel import Session

from app.auth.models import User
from app.common.exceptions import AppException
from app.core.database import get_session
from app.core.security import decode_access_token


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_session),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise AppException(401, "UNAUTHORIZED", "인증 토큰이 필요합니다.")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])
    except (ValueError, KeyError, TypeError) as exc:
        raise AppException(401, "UNAUTHORIZED", "유효하지 않은 토큰입니다.") from exc

    user = db.get(User, user_id)
    if user is None:
        raise AppException(401, "UNAUTHORIZED", "존재하지 않는 사용자입니다.")
    return user

