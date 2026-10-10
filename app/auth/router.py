from fastapi import APIRouter, Depends
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
