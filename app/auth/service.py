"""Track A 구현 대상: register / login 비즈니스 로직. api-spec.md §3.1 참고."""

from sqlmodel import Session

from app.auth.schemas import LoginRequest, RegisterRequest, TokenResponse


def register(session: Session, dto: RegisterRequest) -> TokenResponse:
    raise NotImplementedError
    # TODO: email 중복 확인(409 EMAIL_ALREADY_EXISTS) -> hash_password -> User 저장
    # -> create_access_token -> TokenResponse 반환


def login(session: Session, dto: LoginRequest) -> TokenResponse:
    raise NotImplementedError
    # TODO: email로 User 조회 -> verify_password (실패 시 401 INVALID_CREDENTIALS)
    # -> create_access_token -> TokenResponse 반환
