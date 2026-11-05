from __future__ import annotations

import importlib
from datetime import date
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TransactionFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_id: int
    revision: int
    transaction_date: date
    vendor: str
    description: str
    purpose: str | None
    ocr_text: str | None = Field(default=None, max_length=40_000)
    direction: Literal["purchase", "sales"]
    evidence_type: str
    business_related: bool | None
    total_amount: int
    supply_amount: int | None
    vat_amount: int | None
    tax_treatment: str
    deemed_input_supply: int
    deemed_input_eligible: bool | None
    deemed_input_document_type: str | None


class BusinessFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verification_status: str | None = None
    business_status: str | None = None
    tax_type: Literal["general", "simplified"] | None = None
    tax_profile_confirmed: bool = False
    entity_type: str | None = None
    industry_category: str | None = None
    industry_subtype: str | None = None
    is_sme: bool | None = None
    business_start_date: date | None = None
    business_end_date: date | None = None
    suspension_periods: list[dict[str, date | None]] = Field(default_factory=list)


class AnalysisRequest(BaseModel):
    """Versioned facts passed to a pluggable model adapter; contains no secrets."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["v1"] = "v1"
    run_id: UUID
    transaction: TransactionFacts
    business: BusinessFacts


class LegalReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    title: str
    locator: str | None = None
    url: str | None = None
    effective_date: date | None = None


class AnalysisDecision(BaseModel):
    """Model output is a classification only. It cannot return or calculate money."""

    model_config = ConfigDict(extra="forbid")

    disposition: Literal["DEDUCTIBLE", "NOT_DEDUCTIBLE", "NEEDS_REVIEW", "INSUFFICIENT_INFO"]
    reason: str = Field(min_length=1, max_length=4000)
    missing_information: list[str] = Field(default_factory=list, max_length=30)
    legal_references: list[LegalReference] = Field(default_factory=list, max_length=30)
    analyzer_name: str = Field(min_length=1, max_length=100)
    analyzer_version: str = Field(min_length=1, max_length=100)
    knowledge_version: str | None = Field(default=None, max_length=100)


class PurchaseAnalyzer(Protocol):
    def analyze(self, request: AnalysisRequest) -> AnalysisDecision: ...


class HoldForReviewAnalyzer:
    """Safe default until the teammate's production adapter is configured."""

    def analyze(self, request: AnalysisRequest) -> AnalysisDecision:
        return AnalysisDecision(
            disposition="NEEDS_REVIEW",
            reason="공제 판단 모델이 아직 연결되지 않아 자동 판단을 보류했습니다.",
            analyzer_name="unconfigured",
            analyzer_version="0",
        )


def load_analyzer(spec: str | None) -> PurchaseAnalyzer:
    """Load ``module:factory`` from trusted server configuration, or use safe default."""

    if not spec:
        return HoldForReviewAnalyzer()
    module_name, separator, factory_name = spec.partition(":")
    if not separator or not module_name or not factory_name:
        raise ValueError("DEDUCTION_ANALYZER는 'module:factory' 형식이어야 합니다.")
    factory = getattr(importlib.import_module(module_name), factory_name)
    analyzer = factory()
    if not callable(getattr(analyzer, "analyze", None)):
        raise TypeError("분석 어댑터는 analyze(request) 메서드를 제공해야 합니다.")
    return analyzer
