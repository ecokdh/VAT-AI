"""POST /rag/embed — 관리자 전용 법령 조문 등록."""

import secrets

from fastapi import APIRouter, Depends, Header
from sqlmodel import Session

from app.common.exceptions import AppException
from app.core.config import settings
from app.core.database import get_session
from app.deduction.rag import service
from app.deduction.rag.schemas import LawEmbedIn, LawOut


router = APIRouter(prefix="/rag", tags=["rag"])


def require_admin(x_admin_key: str = Header(default="")) -> None:
    if not settings.ADMIN_API_KEY or not secrets.compare_digest(
        x_admin_key, settings.ADMIN_API_KEY
    ):
        raise AppException(403, "FORBIDDEN", "관리자 키가 올바르지 않습니다.")


@router.post("/embed", response_model=LawOut, status_code=201, dependencies=[Depends(require_admin)])
def embed_law(body: LawEmbedIn, session: Session = Depends(get_session)) -> LawOut:
    return service.embed_law(session, body.source, body.article, body.content)
