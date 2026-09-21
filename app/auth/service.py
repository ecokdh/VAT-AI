from sqlmodel import Session, select

from app.auth.models import User
from app.auth.schemas import AuthResponse, LoginRequest, RegisterRequest, UserOut
from app.common.exceptions import AppException
from app.core.security import create_access_token, hash_password, verify_password


def _to_user_out(user: User) -> UserOut:
    return UserOut(id=str(user.id), email=user.email, name=user.name, created_at=user.created_at)


def register_user(db: Session, data: RegisterRequest) -> AuthResponse:
    existing = db.exec(select(User).where(User.email == data.email)).first()
    if existing:
        raise AppException(409, "EMAIL_ALREADY_EXISTS", "이미 가입된 이메일입니다.")

    user = User(email=data.email, password_hash=hash_password(data.password), name=data.name)
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id, user.email)
    return AuthResponse(access_token=token, user=_to_user_out(user))


def login_user(db: Session, data: LoginRequest) -> AuthResponse:
    user = db.exec(select(User).where(User.email == data.email)).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise AppException(401, "INVALID_CREDENTIALS", "이메일 또는 비밀번호가 올바르지 않습니다.")

    token = create_access_token(user.id, user.email)
    return AuthResponse(access_token=token, user=_to_user_out(user))