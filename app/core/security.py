"""비밀번호 해싱(bcrypt) + JWT 발급/검증(python-jose)."""

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.common.exceptions import AppException
from app.core.config import settings


BCRYPT_MAX_PASSWORD_BYTES = 72


def _validate_password_bytes(plain_password: str) -> bytes:
    if not plain_password:
        raise AppException(400, "VALIDATION_ERROR", "비밀번호는 비어 있을 수 없습니다.")
    encoded = plain_password.encode("utf-8")
    if len(encoded) > BCRYPT_MAX_PASSWORD_BYTES:
        raise AppException(
            400,
            "VALIDATION_ERROR",
            "비밀번호는 UTF-8 기준 72바이트 이하로 입력해야 합니다.",
        )
    return encoded


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(_validate_password_bytes(plain_password), bcrypt.gensalt()).decode(
        "utf-8"
    )


def verify_password(plain_password: str, password_hash: str) -> bool:
    if not plain_password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: str, email: str) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_EXPIRE_MINUTES
    )
    payload = {"sub": str(user_id), "email": email, "exp": expires_at}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as exc:
        raise ValueError("유효하지 않은 인증 토큰입니다.") from exc

    if not isinstance(payload.get("sub"), str) or not isinstance(
        payload.get("email"), str
    ):
        raise ValueError("유효하지 않은 인증 토큰입니다.")
    return payload
