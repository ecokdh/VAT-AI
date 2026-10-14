import uuid
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field, FiniteFloat, model_validator, field_validator
import json



def restored_review(raw):
    import copy
    review=copy.deepcopy(raw.get('review'))
    if not review or not review.get('document'):return review
    originals=(raw.get('document') or {}).get('items',[]);used=set()
    for item in review['document'].get('items',[]):
        if 'source_row' in item:
            if item['source_row'] is not None:used.add(item['source_row'])
            continue
        candidates=[k for k,o in enumerate(originals) if k not in used and item.get('raw_name') is not None
            and item['raw_name']==o.get('raw_name',o.get('name'))
            and all(item.get(f)==o.get(f) for f in ('quantity','unit_price','line_amount','row_type'))]
        if len(candidates)==1:item['source_row']=candidates[0];used.add(candidates[0])
    return review

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
    status: Literal["processing", "done", "needs_edit", "unsupported", "retake", "failed"]
    created_at: datetime
    doc_type: Optional[str] = "uninspected"
    support_status: Optional[str] = "uninspected"
    readability_issues: list[str] = Field(default_factory=list)
    affected_regions: list[str] = Field(default_factory=list)
    issue_code: Optional[str] = None
    guide_message: Optional[str] = None
    classification_version: Optional[str] = None

    @field_validator("doc_type", mode="before")
    @classmethod
    def default_doc_type(cls, v):
        return v if v is not None else "uninspected"

    @field_validator("support_status", mode="before")
    @classmethod
    def default_support_status(cls, v):
        return v if v is not None else "uninspected"

    @computed_field
    @property
    def recognition(self) -> dict | None:
        try:
            raw = json.loads(self.ocr_raw or '')
            if not isinstance(raw, dict) or raw.get('engine') != 'luna_low':
                return None
            review = restored_review(raw) or {}
            if review.get('document') is not None:
                return {**raw, 'original_document': raw.get('document'), 'document': {**(raw.get('document') or {}), **review['document'], 'conflicts': [], 'uncertain': []}, 'value_source': 'user_review'}
            return raw
        except (ValueError, TypeError):
            return None

    @computed_field
    @property
    def review(self) -> dict | None:
        try:
            raw = json.loads(self.ocr_raw or '')
            return restored_review(raw) if isinstance(raw, dict) else None
        except (ValueError, TypeError):
            return None


class ReceiptSummary(BaseModel):
    """api-spec.md §3.2 — GET /receipts 목록 항목."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    vendor: Optional[str]
    amount: Optional[float]
    date: Optional[date]
    status: Literal["processing", "done", "needs_edit", "unsupported", "retake", "failed"]
    created_at: datetime
    doc_type: Optional[str] = "uninspected"
    support_status: Optional[str] = "uninspected"
    issue_code: Optional[str] = None
    guide_message: Optional[str] = None

    @field_validator("doc_type", mode="before")
    @classmethod
    def default_summary_doc_type(cls, v):
        return v if v is not None else "uninspected"

    @field_validator("support_status", mode="before")
    @classmethod
    def default_summary_support_status(cls, v):
        return v if v is not None else "uninspected"


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


class ReviewedFields(BaseModel):
    model_config = ConfigDict(extra='forbid')
    vendor: str | None = Field(default=None, max_length=255)
    branch: str | None = Field(default=None, max_length=255)
    business_number: str | None = Field(default=None, max_length=30)
    transaction_datetime: str | None = Field(default=None, max_length=50)
    printed_total_amount: FiniteFloat | None = None
    payment_amount: FiniteFloat | None = None
    supply_amount: FiniteFloat | None = None
    taxable_supply_amount: FiniteFloat | None = None
    vat_amount: FiniteFloat | None = None
    tax_exempt_amount: FiniteFloat | None = None
    discount_amount: FiniteFloat | None = None
    subtotal_amount: FiniteFloat | None = None


class ReviewedItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=500)
    raw_name: str | None = Field(default=None, max_length=500)
    source_row: int | None = Field(default=None,strict=True,ge=0)
    quantity: FiniteFloat | None = None
    unit_price: FiniteFloat | None = None
    line_amount: FiniteFloat | None = None
    row_type: Literal['item', 'option', 'discount'] = 'item'
    parent_row: int | None = None


class ReviewedDocument(BaseModel):
    model_config = ConfigDict(extra='forbid')
    fields: ReviewedFields
    items: list[ReviewedItem] = Field(default_factory=list, max_length=500)

    @model_validator(mode='after')
    def valid_parent(self):
        for i, item in enumerate(self.items):
            p = item.parent_row
            if item.row_type == 'item' and p is not None:
                raise ValueError('일반 상품에는 연결 상품을 지정할 수 없습니다.')
            if p is not None and (p < 0 or p >= len(self.items) or p == i or self.items[p].row_type != 'item'):
                raise ValueError('옵션·할인의 연결 상품을 확인해 주세요.')
        return self


class ExtractionConfirmation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    details: ReceiptDetails | None = None
    vendor: str = Field(min_length=1, max_length=255)
    amount: int = Field(ge=0)
    date: date
    document: ReviewedDocument | None = None
    question_answers: dict[str, str] = Field(default_factory=dict)
    purpose: str | None = Field(default=None, max_length=1000)
    evidence_type: Literal['tax_invoice','card_receipt','cash_receipt','tax_free_receipt','manual','unknown'] = 'unknown'
    business_related: bool | None = None
    tax_treatment: Literal['standard','zero','exempt','unknown'] = 'unknown'

    @model_validator(mode='after')
    def matching_core(self):
        if self.document is not None:
            f = self.document.fields
            if f.vendor is None or f.vendor.strip() != self.vendor.strip():
                raise ValueError('거래처 입력값이 서로 다릅니다.')
            if f.payment_amount != self.amount:
                raise ValueError('결제액 입력값이 서로 다릅니다.')
            try:
                parsed = date.fromisoformat((f.transaction_datetime or '')[:10])
            except ValueError:
                raise ValueError('거래일을 확인해 주세요.')
            if parsed != self.date:
                raise ValueError('거래일 입력값이 서로 다릅니다.')
        return self


class ReceiptRetryAccepted(BaseModel):
    receipt_id: int
    job_id: uuid.UUID
    status: Literal["PENDING"]
    attempt: int

