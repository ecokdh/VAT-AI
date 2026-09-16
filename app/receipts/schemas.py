import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class ReceiptOut(BaseModel):
    """api-spec.md §3.2 — POST /receipts, GET /receipts/{id} 응답."""

    id: int
    user_id: uuid.UUID
    image_url: str
    ocr_raw: Optional[str]
    vendor: Optional[str]
    amount: Optional[float]
    date: Optional[date]
    status: str  # "done" | "failed"
    created_at: datetime


class ReceiptSummary(BaseModel):
    """api-spec.md §3.2 — GET /receipts 목록 항목."""

    id: int
    vendor: Optional[str]
    amount: Optional[float]
    date: Optional[date]
    status: str
    created_at: datetime
