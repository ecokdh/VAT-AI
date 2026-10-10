"""User registration and login services."""

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session, select

from app.auth.models import ConsentRecord, User
from app.auth.schemas import AuthResponse, LoginRequest, RegisterRequest, UserOut
from app.business.models import BusinessProfile
from app.business.schemas import BusinessProfileOut
from app.business.service import verify_business
from app.common.exceptions import AppException
from app.core.security import create_access_token, hash_password, verify_password


def _to_business_out(profile: BusinessProfile) -> BusinessProfileOut:
    return BusinessProfileOut(
        id=str(profile.id),
        user_id=str(profile.user_id),
        business_number=profile.business_number,
        business_name=profile.business_name,
        business_status=profile.business_status,
        business_status_code=profile.business_status_code,
        tax_type=profile.tax_type,
        tax_type_code=profile.tax_type_code,
        end_date=profile.end_date,
        verification_status=profile.verification_status,
        verified_at=profile.verified_at,
        created_at=profile.created_at,
    )


def _to_user_out(user: User, profile: BusinessProfile | None = None) -> UserOut:
    return UserOut(
        id=str(user.id),
        email=user.email,
        name=user.name,
        created_at=user.created_at,
        business=_to_business_out(profile) if profile is not None else None,
    )


def get_user_out(db: Session, user: User) -> UserOut:
    profile = db.exec(select(BusinessProfile).where(BusinessProfile.user_id == user.id)).first()
    return _to_user_out(user, profile)


def is_email_available(db: Session, email: str) -> bool:
    normalized_email = email.strip().lower()
    return db.exec(select(User).where(User.email == normalized_email)).first() is None


def register_user(db: Session, data: RegisterRequest) -> AuthResponse:
    email = str(data.email).strip().lower()
    name = data.name.strip()
    if not name:
        raise AppException(400, "VALIDATION_ERROR", "이름은 비어 있을 수 없습니다.")
    if not data.terms_accepted or not data.privacy_accepted:
        raise AppException(400, "CONSENT_REQUIRED", "서비스 이용약관과 개인정보 처리방침에 동의해야 가입할 수 있습니다.")
    if db.exec(select(User).where(User.email == email)).first() is not None:
        raise AppException(409, "EMAIL_ALREADY_EXISTS", "이미 가입된 이메일입니다.")

    business_name = data.business_name.strip()
    if not business_name:
        raise AppException(400, "VALIDATION_ERROR", "사업자명은 비어 있을 수 없습니다.")
    verification = verify_business(data.business_number)
    if not verification.verified:
        raise AppException(502, "BUSINESS_API_INVALID_RESPONSE", "사업자정보 확인에 실패했습니다.")

    consent_recorded_at = datetime.now(timezone.utc)
    user = User(
        email=email,
        password_hash=hash_password(data.password),
        name=name,
    )
    user_flushed = False
    try:
        db.add(user)
        db.flush()
        user_flushed = True
        profile = BusinessProfile(
            user_id=user.id,
            business_number=verification.business_number,
            business_name=business_name,
            business_status=verification.business_status,
            business_status_code=verification.business_status_code,
            tax_type=verification.tax_type,
            tax_type_code=verification.tax_type_code,
            end_date=verification.end_date,
            verification_status="status_checked",
            verified_at=datetime.utcnow(),
        )
        db.add(profile)
        db.add_all([
            ConsentRecord(
                user_id=user.id,
                consent_type="terms",
                accepted=data.terms_accepted,
                recorded_at=consent_recorded_at,
            ),
            ConsentRecord(
                user_id=user.id,
                consent_type="privacy",
                accepted=data.privacy_accepted,
                recorded_at=consent_recorded_at,
            ),
            ConsentRecord(
                user_id=user.id,
                consent_type="marketing",
                accepted=data.marketing_accepted,
                recorded_at=consent_recorded_at,
            ),
        ])
        db.commit()
        db.refresh(user)
        db.refresh(profile)
    except IntegrityError as exc:
        db.rollback()
        if not user_flushed:
            raise AppException(409, "EMAIL_ALREADY_EXISTS", "이미 가입된 이메일입니다.") from exc
        raise AppException(500, "DATABASE_ERROR", "가입 정보 저장에 실패했습니다.") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise AppException(500, "DATABASE_ERROR", "사용자 저장에 실패했습니다.") from exc
    except Exception:
        db.rollback()
        raise

    return AuthResponse(
        access_token=create_access_token(user.id, user.email),
        user=_to_user_out(user, profile),
    )


def login_user(db: Session, data: LoginRequest) -> AuthResponse:
    email = str(data.email).strip().lower()
    user = db.exec(select(User).where(User.email == email)).first()
    if user is None or not verify_password(data.password, user.password_hash):
        raise AppException(401, "INVALID_CREDENTIALS", "이메일 또는 비밀번호가 올바르지 않습니다.")
    return AuthResponse(
        access_token=create_access_token(user.id, user.email),
        user=get_user_out(db, user),
    )
