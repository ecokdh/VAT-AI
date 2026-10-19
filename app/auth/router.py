from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from app.auth import service
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.auth.schemas import (
    AuthResponse,
    EmailAvailabilityRequest,
    EmailAvailabilityResponse,
    LoginRequest,
    RegisterRequest,
    UserOut,
    ProfileUpdate,
)
from app.core.database import get_session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/email-availability", response_model=EmailAvailabilityResponse)
def email_availability(data: EmailAvailabilityRequest, db: Session = Depends(get_session)):
    return {"available": service.is_email_available(db, str(data.email))}


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(data: RegisterRequest, db: Session = Depends(get_session)):
    return service.register_user(db, data)


@router.post("/login", response_model=AuthResponse)
def login(data: LoginRequest, db: Session = Depends(get_session)):
    return service.login_user(db, data)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    return service.get_user_out(db, current_user)


@router.patch("/me", response_model=UserOut)
def update_me(data: ProfileUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    current_user.nickname = data.nickname
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return service.get_user_out(db, current_user)


from app.auth.schemas import PasswordResetRequest, PasswordResetConfirmation
from app.auth import password_reset


@router.post("/forgot-password", status_code=202)
def forgot_password(data: PasswordResetRequest, request: Request, db: Session = Depends(get_session)):
    return password_reset.request_reset(db, str(data.email), request.client.host if request.client else "unknown")


@router.post("/reset-password")
def reset_password(data: PasswordResetConfirmation, db: Session = Depends(get_session)):
    return password_reset.reset_password(db, data.token, data.password)


@router.post("/ocr-guide-seen", response_model=UserOut)
def mark_ocr_guide_seen(user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    user.ocr_guide_seen = True
    db.add(user)
    db.commit()
    return service.get_user_out(db, user)
