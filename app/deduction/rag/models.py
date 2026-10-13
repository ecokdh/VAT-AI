from datetime import datetime, timezone
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Text
from sqlmodel import Field, SQLModel


EMBEDDING_DIM = 1536  # text-embedding-3-small


class LawEmbedding(SQLModel, table=True):
    """RAG 검색 대상 법령 조문 (기획서 law_embeddings 테이블)."""

    __tablename__ = "law_embeddings"

    id: Optional[int] = Field(default=None, primary_key=True)
    source: str = Field(nullable=False)  # 법령명 (예: 부가가치세법)
    article: Optional[str] = Field(default=None)  # 조문번호 (예: 제39조)
    content: str = Field(sa_column=Column(Text, nullable=False))
    embedding: list[float] = Field(sa_column=Column(Vector(EMBEDDING_DIM), nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)
