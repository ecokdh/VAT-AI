"""최소 인증 흐름. B트랙 API가 실제 JWT 사용자와 연결되도록 구현한다."""

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session, select

from app.auth.models import User
from app.auth.schemas import LoginRequest, RegisterRequest, TokenResponse
from app.common.exceptions import AppError
from app.core.security import create_access_token, hash_password, verify_password


def register(session: Session, dto: RegisterRequest) -> TokenResponse:
    email = str(dto.email).strip().lower()
    name = dto.name.strip()
    if not name:
        raise AppError(400, "VALIDATION_ERROR", "이름은 비어 있을 수 없습니다.")
    if session.exec(select(User).where(User.email == email)).first() is not None:
        raise AppError(409, "EMAIL_ALREADY_EXISTS", "이미 가입된 이메일입니다.")

    user = User(email=email, password_hash=hash_password(dto.password), name=name)
    try:
        session.add(user)
        session.commit()
        session.refresh(user)
    except IntegrityError as exc:
        session.rollback()
        raise AppError(409, "EMAIL_ALREADY_EXISTS", "이미 가입된 이메일입니다.") from exc
    except SQLAlchemyError as exc:
        session.rollback()
        raise AppError(500, "DATABASE_ERROR", "사용자 저장에 실패했습니다.") from exc

    return TokenResponse(
        access_token=create_access_token(str(user.id), user.email), user=user
    )


def login(session: Session, dto: LoginRequest) -> TokenResponse:
    email = str(dto.email).strip().lower()
    user = session.exec(select(User).where(User.email == email)).first()
    if user is None or not verify_password(dto.password, user.password_hash):
        raise AppError(
            401,
            "INVALID_CREDENTIALS",
            "이메일 또는 비밀번호가 올바르지 않습니다.",
        )
    return TokenResponse(
        access_token=create_access_token(str(user.id), user.email), user=user
    )

