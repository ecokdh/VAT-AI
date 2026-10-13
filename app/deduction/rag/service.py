"""법령 조문 임베딩 저장과 pgvector 유사도 검색."""

from collections.abc import Iterable

from sqlmodel import Session, select

from app.common.exceptions import AppException
from app.core.config import settings
from app.deduction.rag.models import LawEmbedding
from app.deduction.rag.schemas import LawOut


def get_embedding(text: str) -> list[float]:
    return get_embeddings([text])[0]


def get_embeddings(texts: list[str]) -> list[list[float]]:
    try:
        from openai import OpenAI

        response = OpenAI(api_key=settings.OPENAI_API_KEY).embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=texts,
        )
    except Exception as exc:
        raise AppException(502, "EXTERNAL_API_ERROR", "임베딩 API 호출에 실패했습니다.") from exc

    return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]


def embed_law(session: Session, source: str, article: str | None, content: str) -> LawOut:
    law = LawEmbedding(
        source=source,
        article=article,
        content=content,
        embedding=get_embedding(content),
    )
    session.add(law)
    session.commit()
    session.refresh(law)

    return _to_out(law)


def search_laws(
    session: Session,
    query: str,
    top_k: int = 5,
    exclude_ids: Iterable[int] = (),
) -> list[LawOut]:
    """코사인 거리(<=>) 오름차순으로 관련 조문을 찾는다. PostgreSQL + pgvector 전용."""
    statement = select(LawEmbedding).order_by(
        LawEmbedding.embedding.cosine_distance(get_embedding(query))
    )

    exclude_ids = list(exclude_ids)
    if exclude_ids:
        statement = statement.where(LawEmbedding.id.not_in(exclude_ids))

    return [_to_out(law) for law in session.exec(statement.limit(top_k)).all()]


def get_laws(session: Session, refs: Iterable[tuple[str, str]]) -> list[LawOut]:
    """(법령명, 조문) 목록을 그 순서대로 조회한다. 등록되지 않은 조문은 건너뛴다."""
    refs = list(refs)
    statement = select(LawEmbedding).where(LawEmbedding.source.in_({source for source, _ in refs}))
    found = {(law.source, law.article): law for law in session.exec(statement).all()}
    return [_to_out(found[ref]) for ref in refs if ref in found]


def _to_out(law: LawEmbedding) -> LawOut:
    return LawOut(id=law.id, source=law.source, article=law.article, content=law.content)
