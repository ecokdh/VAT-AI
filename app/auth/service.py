"""A트랙 인증 계약을 사용하는 사용자 등록·로그인 서비스."""

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session, select

from app.auth.models import User
from app.auth.schemas import AuthResponse, LoginRequest, RegisterRequest, UserOut
from app.common.exceptions import AppException
from app.core.security import create_access_token, hash_password, verify_password


def _to_user_out(user: User) -> UserOut:
    return UserOut(
        id=str(user.id),
        email=user.email,
        name=user.name,
        created_at=user.created_at,
    )


def register_user(db: Session, data: RegisterRequest) -> AuthResponse:
    email = str(data.email).strip().lower()
    name = data.name.strip()
    if not name:
        raise AppException(400, "VALIDATION_ERROR", "이름은 비어 있을 수 없습니다.")
    if db.exec(select(User).where(User.email == email)).first() is not None:
        raise AppException(409, "EMAIL_ALREADY_EXISTS", "이미 가입된 이메일입니다.")

    user = User(email=email, password_hash=hash_password(data.password), name=name)
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise AppException(409, "EMAIL_ALREADY_EXISTS", "이미 가입된 이메일입니다.") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise AppException(500, "DATABASE_ERROR", "사용자 저장에 실패했습니다.") from exc

    return AuthResponse(
        access_token=create_access_token(user.id, user.email),
        user=_to_user_out(user),
    )


def login_user(db: Session, data: LoginRequest) -> AuthResponse:
    email = str(data.email).strip().lower()
    user = db.exec(select(User).where(User.email == email)).first()
    if user is None or not verify_password(data.password, user.password_hash):
        raise AppException(
            401,
            "INVALID_CREDENTIALS",
            "이메일 또는 비밀번호가 올바르지 않습니다.",
        )
    return AuthResponse(
        access_token=create_access_token(user.id, user.email),
        user=_to_user_out(user),
    )

