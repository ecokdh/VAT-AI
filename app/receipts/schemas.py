import uuid
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ReceiptOut(BaseModel):
    """api-spec.md §3.2 — POST /receipts, GET /receipts/{id} 응답."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: uuid.UUID
    image_url: str
    ocr_raw: Optional[str]
    vendor: Optional[str]
    amount: Optional[float]
    date: Optional[date]
    status: Literal["processing", "done", "failed"]
    created_at: datetime


class ReceiptSummary(BaseModel):
    """api-spec.md §3.2 — GET /receipts 목록 항목."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    vendor: Optional[str]
    amount: Optional[float]
    date: Optional[date]
    status: Literal["processing", "done", "failed"]
    created_at: datetime


class ReceiptProcessingOut(ReceiptOut):
    """v2-only receipt details with replaceable OCR pipeline progress."""

    processing_stage: Optional[str]
    processing_progress: int
    stage_statuses: dict[str, str]
    ocr_warnings: list[str]
    ocr_pipeline_name: Optional[str]
    ocr_pipeline_version: Optional[str]
    ocr_missing_fields: list[str]
    extraction_confirmed: bool
    ocr_user_attempts: int
    retention_status: str


class ExtractionConfirmation(BaseModel):
    vendor: str = Field(min_length=1, max_length=255)
    amount: int = Field(ge=0)
    date: date


class ReceiptRetryAccepted(BaseModel):
    receipt_id: int
    job_id: uuid.UUID
    status: Literal["PENDING"]
    attempt: int

