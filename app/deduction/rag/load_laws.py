"""data/laws.json(fetch_laws 결과)을 임베딩해 law_embeddings 테이블에 일괄 등록한다.

실행: python -m app.deduction.rag.load_laws
같은 source의 기존 조문은 지우고 다시 넣는다(법령 개정 시 재실행).
"""

import json
from pathlib import Path

from sqlmodel import Session, delete

from app.core.database import engine
from app.deduction.rag.fetch_laws import OUTPUT_PATH
from app.deduction.rag.models import LawEmbedding
from app.deduction.rag.schemas import LawEmbedIn
from app.deduction.rag.service import get_embeddings


BATCH_SIZE = 100  # 임베딩 API 한 번 호출에 보낼 조문 수


def load_laws(session: Session, laws: list[LawEmbedIn]) -> int:
    sources = {law.source for law in laws}
    session.exec(delete(LawEmbedding).where(LawEmbedding.source.in_(sources)))

    for start in range(0, len(laws), BATCH_SIZE):
        batch = laws[start:start + BATCH_SIZE]
        embeddings = get_embeddings([law.content for law in batch])
        session.add_all(
            LawEmbedding(source=law.source, article=law.article, content=law.content, embedding=embedding)
            for law, embedding in zip(batch, embeddings)
        )
        print(f"{start + len(batch)}/{len(laws)}")

    session.commit()
    return len(laws)


def main(path: Path = OUTPUT_PATH) -> None:
    if engine.dialect.name != "postgresql":
        raise SystemExit("law_embeddings 검색은 PostgreSQL + pgvector 전용입니다. DB_URL을 확인하세요.")

    laws = [LawEmbedIn(**item) for item in json.loads(path.read_text(encoding="utf-8"))]
    with Session(engine) as session:
        count = load_laws(session, laws)
    print(f"총 {count}개 조문 등록 완료")


if __name__ == "__main__":
    main()
