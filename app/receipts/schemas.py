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


class ReceiptLineItem(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    quantity: float | None = Field(default=None, ge=0)
    unit_price: int | None = Field(default=None, ge=0)
    amount: int | None = Field(default=None, ge=0)


class AdditionalReceiptField(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    value: str = Field(max_length=1000)


class ReceiptDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    business_number: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=300)
    phone: str | None = Field(default=None, max_length=40)
    payment_method: str | None = Field(default=None, max_length=40)
    approval_number: str | None = Field(default=None, max_length=40)
    receipt_number: str | None = Field(default=None, max_length=60)
    supply_amount: int | None = Field(default=None, ge=0)
    vat_amount: int | None = Field(default=None, ge=0)
    tax_free_amount: int | None = Field(default=None, ge=0)
    items: list[ReceiptLineItem] = Field(default_factory=list, max_length=100)
    additional_fields: list[AdditionalReceiptField] = Field(default_factory=list, max_length=50)


class ReceiptProcessingOut(ReceiptOut):
    """v2-only receipt details with replaceable OCR pipeline progress."""

    details: ReceiptDetails = Field(default_factory=ReceiptDetails)
    direction: Literal["purchase", "sales"]
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
    details: ReceiptDetails | None = None
    vendor: str = Field(min_length=1, max_length=255)
    amount: int = Field(ge=0)
    date: date


class ReceiptRetryAccepted(BaseModel):
    receipt_id: int
    job_id: uuid.UUID
    status: Literal["PENDING"]
    attempt: int

