from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

DateType = date


SourceStatus = Literal["확인 완료", "해당 없음 확인", "자료 없음", "검토 필요"]


class SourceUpdate(BaseModel):
    status: SourceStatus
    query_start: DateType | None = None
    query_end: DateType | None = None
    basis: str | None = Field(default=None, max_length=120)
    document_ids: list[int] = Field(default_factory=list, max_length=100)
    expected_document_ids: list[int] | None = Field(default=None, max_length=100)
    reason: str | None = Field(default=None, max_length=1000)


class ManualSalesInput(BaseModel):
    input_key: str = Field(min_length=1, max_length=120)
    source: Literal["pg", "unissued_sales"]
    date: DateType | None = None
    description: str = Field(default="", max_length=255)
    reference: str | None = Field(default=None, max_length=120)
    payment_method: str = Field(default="", max_length=80)
    tax_treatment: str = Field(default="", max_length=40)
    supply_amount: int | None = Field(default=None, ge=0)
    vat_amount: int | None = Field(default=None, ge=0)
    total_amount: int | None = Field(default=None, ge=0)
    fee_amount: int | None = Field(default=None, ge=0)
    deposit_amount: int | None = Field(default=None, ge=0)
    supporting_evidence: str = Field(min_length=1, max_length=2000)


class SalesFeedback(BaseModel):
    request_id: str = Field(min_length=1, max_length=120)
    issue_id: str = Field(min_length=1, max_length=64)
    action: Literal["중복 확인", "누락 확인", "해당 없음", "금액 정정"]
    evidence: str = Field(min_length=1, max_length=2000)
    original_reference: str | None = Field(default=None, max_length=120)
    original_period: str | None = Field(default=None, max_length=16)
    amount: int | None = Field(default=None, ge=0)
    supply_amount: int | None = None
    vat_amount: int | None = None
    total_amount: int | None = None


class FinalizeSalesCase(BaseModel):
    confirm_changed_sources: bool = False
