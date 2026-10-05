import json
import uuid
from datetime import date as date_type
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator
from app.receipts.document import StructuredItem, DocumentFacts, evidence_validation


ReceiptStatus = Literal["done", "failed", "retake", "needs_edit"]


class ItemAmountIn(BaseModel):
    item_index: int = Field(ge=0, strict=True)
    quantity: Optional[FiniteFloat] = Field(default=None, gt=0, strict=True)
    line_amount: Optional[FiniteFloat] = Field(default=None, ge=0, strict=True)
    unit_price: Optional[FiniteFloat] = Field(default=None, ge=0, strict=True)


class ItemAmountOut(BaseModel):
    item_index: int
    quantity: Optional[FiniteFloat] = None
    line_amount: Optional[FiniteFloat] = None
    unit_price: Optional[FiniteFloat] = None
    item_name: str
    sources: dict[str, dict[str, str]] = Field(default_factory=dict)


class ReceiptOut(BaseModel):
    """POST /receipts, GET /receipts/{id} 응답."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: uuid.UUID
    image_url: str
    ocr_raw: Optional[str]
    vendor: Optional[str]
    amount: Optional[float]
    date: Optional[date_type]
    status: ReceiptStatus
    quality_reason: Optional[str] = None
    business_number: Optional[str] = None
    supply_amount: Optional[float] = None
    vat_amount: Optional[float] = None
    taxable_supply_amount: Optional[float] = None
    tax_exempt_amount: Optional[float] = None
    transaction_amount: Optional[float] = None
    payment_amount: Optional[float] = None
    subtotal_amount: Optional[float] = None
    item_amounts: list[ItemAmountOut] = Field(default_factory=list)
    money_schema_version: int = 1
    money_sources: dict[str, dict[str, Any]] = {}
    items: list[str] = []
    ocr_original: Optional[str] = None
    confirmed: bool = False
    revision: int = 1
    document: DocumentFacts = Field(default_factory=DocumentFacts)
    line_items: list[StructuredItem] = Field(default_factory=list)
    transaction_id: str | None = None
    evidence_validation: dict = Field(default_factory=dict)
    workflow_status: str = "NEEDS_OCR_CORRECTION"
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def items_from_json(cls, value):
        if hasattr(value, "items_json") and not isinstance(value, dict):
            data = {
                field: getattr(value, field)
                for field in cls.model_fields
                if field not in ("items", "line_items") and hasattr(value, field)
            }
            data["items"] = _parse_items(getattr(value, "items_json", None))
            data["money_sources"] = json.loads(getattr(value, "money_sources_json", None) or "{}")
            data["item_amounts"] = json.loads(getattr(value, "item_amounts_json", None) or "[]")
            data["line_items"] = [json.loads(row.data_json) | {"id": row.id} for row in sorted(value.line_items, key=lambda row: row.position)]
            data["document"] = json.loads(value.document_json or "{}")
            data["evidence_validation"] = evidence_validation(value, DocumentFacts.model_validate(data["document"]))
            data["workflow_status"] = "OCR_CONFIRMED" if value.confirmed else "NEEDS_OCR_CORRECTION"
            return data
        if isinstance(value, dict) and "items" not in value:
            value = dict(value)
            value["items"] = _parse_items(value.get("items_json"))
        return value


def _parse_items(raw: object) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if not isinstance(raw, str):
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


class ReceiptSummary(BaseModel):
    """GET /receipts 목록 항목."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    transaction_id: str | None = None
    revision: int = 1
    vendor: Optional[str]
    amount: Optional[float]
    date: Optional[date_type]
    status: ReceiptStatus
    quality_reason: Optional[str] = None
    supply_amount: Optional[float] = None
    vat_amount: Optional[float] = None
    taxable_supply_amount: Optional[float] = None
    tax_exempt_amount: Optional[float] = None
    transaction_amount: Optional[float] = None
    payment_amount: Optional[float] = None
    subtotal_amount: Optional[float] = None
    money_schema_version: int = 1
    confirmed: bool = False
    created_at: datetime


class ReceiptOcrUpdate(BaseModel):
    base_revision: int = Field(ge=1, strict=True)
    field_states: dict[str, Literal["READ", "ABSENT", "FAILED", "UNREVIEWED", "NOT_APPLICABLE"]] = Field(default_factory=dict)
    line_items: list[StructuredItem] | None = None
    document: DocumentFacts | None = None
    vendor: Optional[str] = None
    business_number: Optional[str] = None
    date: Optional[date_type] = None
    supply_amount: Optional[float] = None
    vat_amount: Optional[float] = None
    taxable_supply_amount: Optional[float] = None
    tax_exempt_amount: Optional[float] = None
    transaction_amount: Optional[float] = None
    payment_amount: Optional[float] = None
    subtotal_amount: Optional[float] = None
    item_amounts: Optional[list[ItemAmountIn]] = None
    amount: Optional[float] = None
    items: Optional[list[str]] = None
    # 화면이 마지막으로 불러온 금액. 이 값과 같아야 저장한다.
    base_amount: Optional[float] = None
    base_supply_amount: Optional[float] = None
    base_vat_amount: Optional[float] = None
    base_taxable_supply_amount: Optional[float] = None
    base_tax_exempt_amount: Optional[float] = None
    base_transaction_amount: Optional[float] = None
    base_payment_amount: Optional[float] = None
    base_subtotal_amount: Optional[float] = None
    base_items: Optional[list[str]] = None
    base_item_amounts: Optional[list[dict]] = None

    @model_validator(mode="after")
    def one_item_contract(self):
        allowed = {"vendor", "date", "business_number", "amount", "supply_amount", "vat_amount",
                   "taxable_supply_amount", "tax_exempt_amount", "transaction_amount", "payment_amount", "subtotal_amount"}
        if not set(self.field_states).issubset(allowed):
            raise ValueError("지원하지 않는 영수증 값 상태입니다.")
        if "line_items" in self.model_fields_set and self.model_fields_set.intersection({"items", "item_amounts"}):
            raise ValueError("구조화 품목과 기존 품목 입력을 동시에 수정할 수 없습니다.")
        return self


class ReceiptConfirmIn(BaseModel):
    base_revision: int = Field(ge=1, strict=True)
    confirmed: bool = True

