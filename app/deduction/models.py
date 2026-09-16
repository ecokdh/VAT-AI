from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class Deduction(SQLModel, table=True):
    """api-spec.md §2.3 `deductions` 테이블. receipt_id는 UNIQUE (1:1)."""

    __tablename__ = "deductions"

    id: Optional[int] = Field(default=None, primary_key=True)
    receipt_id: int = Field(foreign_key="receipts.id", unique=True, nullable=False, index=True)
    is_deductible: bool = Field(nullable=False)
    reason: str = Field(nullable=False)
    category: str = Field(nullable=False)
    amount: float = Field(nullable=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)
