"""api-spec.md §3.1 — POST /auth/register, POST /auth/login, GET /auth/me"""

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.auth import service
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.auth.schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.core.database import get_session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(dto: RegisterRequest, session: Session = Depends(get_session)):
    return service.register(session, dto)


@router.post("/login", response_model=TokenResponse)
def login(dto: LoginRequest, session: Session = Depends(get_session)):
    return service.login(session, dto)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
