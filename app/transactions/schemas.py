import uuid
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field as PydanticField, model_validator


class TransactionCreate(BaseModel):
    direction: Literal["purchase", "sales"]
    transaction_date: date
    vendor: str = PydanticField(min_length=1, max_length=255)
    description: str = ""
    purpose: Optional[str] = None
    evidence_type: Literal["tax_invoice", "card_receipt", "cash_receipt", "tax_free_receipt", "manual", "unknown"] = "unknown"
    business_related: Optional[bool] = None
    total_amount: int = PydanticField(ge=0)
    supply_amount: Optional[int] = PydanticField(default=None, ge=0)
    vat_amount: Optional[int] = PydanticField(default=None, ge=0)
    deemed_input_supply: int = PydanticField(default=0, ge=0)
    deemed_input_eligible: Optional[bool] = None
    deemed_input_document_type: Optional[Literal["purchase_invoice", "card_statement", "farmer_direct", "import_declaration"]] = None
    tax_treatment: Literal["standard", "zero", "exempt", "unknown"] = "unknown"

    @model_validator(mode="after")
    def amounts_are_consistent(self):
        if self.supply_amount is not None and self.supply_amount > self.total_amount:
            raise ValueError("공급가액은 거래 총액보다 클 수 없습니다.")
        if self.vat_amount is not None and self.vat_amount > self.total_amount:
            raise ValueError("부가가치세는 거래 총액보다 클 수 없습니다.")
        if self.supply_amount is not None and self.vat_amount is not None:
            if self.supply_amount + self.vat_amount > self.total_amount:
                raise ValueError("공급가액과 세액의 합은 거래 총액보다 클 수 없습니다.")
        return self


class TransactionUpdate(BaseModel):
    transaction_date: Optional[date] = None
    vendor: Optional[str] = PydanticField(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    purpose: Optional[str] = None
    evidence_type: Optional[Literal["tax_invoice", "card_receipt", "cash_receipt", "tax_free_receipt", "manual", "unknown"]] = None
    business_related: Optional[bool] = None
    total_amount: Optional[int] = PydanticField(default=None, ge=0)
    supply_amount: Optional[int] = PydanticField(default=None, ge=0)
    vat_amount: Optional[int] = PydanticField(default=None, ge=0)
    deemed_input_supply: Optional[int] = PydanticField(default=None, ge=0)
    deemed_input_eligible: Optional[bool] = None
    deemed_input_document_type: Optional[Literal["purchase_invoice", "card_statement", "farmer_direct", "import_declaration"]] = None
    tax_treatment: Optional[Literal["standard", "zero", "exempt", "unknown"]] = None


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    receipt_id: Optional[int]
    direction: Literal["purchase", "sales"]
    transaction_date: date
    vendor: str
    description: str
    purpose: Optional[str]
    evidence_type: str
    business_related: Optional[bool]
    total_amount: int
    supply_amount: Optional[int]
    vat_amount: Optional[int]
    deemed_input_supply: int
    deemed_input_eligible: Optional[bool]
    deemed_input_document_type: Optional[str]
    tax_treatment: str
    state: str
    revision: int
    review_status: str
    risk_level: Optional[str]
    deductible_vat: int
    analysis_reason: Optional[str]
    legal_references_json: str
    retention_status: str
    deleted_at: Optional[datetime]
    permanent_delete_requested_at: Optional[datetime]


class AnalysisRunCreate(BaseModel):
    transaction_ids: list[int] = PydanticField(min_length=1, max_length=100)


class AnalysisRunOut(BaseModel):
    id: uuid.UUID
    status: Literal["PENDING", "PROCESSING", "COMPLETED", "FAILED"]
    result_json: Optional[str]
    error_code: Optional[str]
    error_message: Optional[str]
    attempts: int
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]


class TaxEstimateOut(BaseModel):
    period: str
    tax_type: Literal["general", "simplified"]
    status: Literal["COMPLETE", "PARTIAL", "UNAVAILABLE"]
    output_vat: Optional[int]
    eligible_input_vat: Optional[int]
    deemed_input_vat: Optional[int]
    payable_estimate: Optional[int]
    included_transaction_count: int
    caution_transaction_count: int
    uncalculated_transaction_count: int
    rule_version: str
    notes: list[str]
