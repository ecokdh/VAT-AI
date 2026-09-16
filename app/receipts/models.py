import uuid
from datetime import date as date_, datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class Receipt(SQLModel, table=True):
    """api-spec.md §2.2 `receipts` 테이블. status는 "done" | "failed" 둘 중 하나."""

    __tablename__ = "receipts"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)
    image_url: str = Field(nullable=False)
    ocr_raw: Optional[str] = Field(default=None)
    vendor: Optional[str] = Field(default=None)
    amount: Optional[float] = Field(default=None)
    date: Optional[date_] = Field(default=None)
    status: str = Field(nullable=False)  # "done" | "failed"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)
