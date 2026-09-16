from datetime import datetime

from pydantic import BaseModel


class DeductionOut(BaseModel):
    """api-spec.md §3.3 — POST /receipts/{id}/analyze 응답."""

    id: int
    receipt_id: int
    is_deductible: bool
    reason: str
    category: str
    amount: float
    created_at: datetime


class ReportItem(BaseModel):
    receipt_id: int
    vendor: str | None
    amount: float


class ReportOut(BaseModel):
    """api-spec.md §3.3 — GET /reports?period=YYYY-MM 응답."""

    period: str
    total_amount: float
    count: int
    items: list[ReportItem]
