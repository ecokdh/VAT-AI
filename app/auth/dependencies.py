"""다른 트랙(receipts, deduction)이 재사용하는 JWT 사용자 의존성."""

import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session, select

from app.auth.models import User
from app.common.exceptions import AppError
from app.core.database import get_session
from app.core.security import decode_access_token


bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_session),
) -> User:
    if credentials is None:
        raise AppError(401, "UNAUTHORIZED", "인증이 필요합니다.")

    payload = decode_access_token(credentials.credentials)
    try:
        user_id = uuid.UUID(payload["sub"])
    except (ValueError, TypeError) as exc:
        raise AppError(401, "UNAUTHORIZED", "유효하지 않은 인증 토큰입니다.") from exc

    user = session.exec(select(User).where(User.id == user_id)).first()
    if user is None:
        raise AppError(401, "UNAUTHORIZED", "사용자를 찾을 수 없습니다.")
    return user

