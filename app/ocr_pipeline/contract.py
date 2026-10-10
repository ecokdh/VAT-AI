from __future__ import annotations

import importlib
from datetime import date
from enum import StrEnum
from typing import Callable, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class OcrStage(StrEnum):
    PHOTO_QUALITY = "photo_quality"
    TEXT_RECOGNITION = "text_recognition"
    TRANSACTION_EXTRACTION = "transaction_extraction"
    MISSING_FIELD_CHECK = "missing_field_check"


class OcrStageStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class OcrStageUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: OcrStage
    status: OcrStageStatus
    progress_percent: int = Field(ge=0, le=100)
    message: str | None = Field(default=None, max_length=500)


class OcrPipelineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["v1"] = "v1"
    receipt_id: int
    content_type: Literal["image/jpeg", "image/png"]
    image_bytes: bytes


class OcrPipelineResult(BaseModel):
    """Normalized extraction. Partial fields are allowed so a person can correct them."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["COMPLETED", "PARTIAL", "FAILED"]
    vendor: str | None = Field(default=None, max_length=255)
    amount: int | None = Field(default=None, ge=0)
    transaction_date: date | None = None
    raw_text: str | None = Field(default=None, max_length=40_000)
    field_confidences: dict[str, float] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list, max_length=50)
    warnings: list[str] = Field(default_factory=list, max_length=50)
    retention_status: Literal["required", "not_required", "under_review"] = "under_review"
    pipeline_name: str = Field(min_length=1, max_length=100)
    pipeline_version: str = Field(min_length=1, max_length=100)


ProgressCallback = Callable[[OcrStageUpdate], None]


class OcrPipeline(Protocol):
    def process(self, request: OcrPipelineInput, report_progress: ProgressCallback) -> OcrPipelineResult: ...


class ClovaPipelineAdapter:
    """Compatibility adapter for the current single-call CLOVA extractor."""

    def process(self, request: OcrPipelineInput, report_progress: ProgressCallback) -> OcrPipelineResult:
        report_progress(OcrStageUpdate(stage=OcrStage.PHOTO_QUALITY, status=OcrStageStatus.COMPLETED,
                                       progress_percent=15, message="업로드 시 이미지 형식과 품질을 확인했습니다."))
        report_progress(OcrStageUpdate(stage=OcrStage.TEXT_RECOGNITION, status=OcrStageStatus.PROCESSING,
                                       progress_percent=25, message="증빙 글자를 인식하고 있습니다."))
        from app.receipts.ocr_client import extract_receipt_sync

        result = extract_receipt_sync(request.image_bytes, request.content_type)
        report_progress(OcrStageUpdate(stage=OcrStage.TEXT_RECOGNITION, status=OcrStageStatus.COMPLETED,
                                       progress_percent=60, message="글자 인식이 끝났습니다."))
        report_progress(OcrStageUpdate(stage=OcrStage.TRANSACTION_EXTRACTION, status=OcrStageStatus.PROCESSING,
                                       progress_percent=65, message="거래 정보와 금액을 정리하고 있습니다."))
        report_progress(OcrStageUpdate(stage=OcrStage.TRANSACTION_EXTRACTION,
                                       status=OcrStageStatus.COMPLETED if result else OcrStageStatus.FAILED,
                                       progress_percent=80, message="필수 거래 필드를 추출하지 못했습니다." if result is None else None))
        missing = []
        if result is None or not result.vendor:
            missing.append("vendor")
        if result is None or result.amount is None:
            missing.append("amount")
        if result is None or result.date is None:
            missing.append("transaction_date")
        report_progress(OcrStageUpdate(stage=OcrStage.MISSING_FIELD_CHECK,
                                       status=OcrStageStatus.PROCESSING, progress_percent=85,
                                       message="누락되거나 확인이 필요한 항목을 점검하고 있습니다."))
        report_progress(OcrStageUpdate(stage=OcrStage.MISSING_FIELD_CHECK,
                                       status=OcrStageStatus.COMPLETED if not missing else OcrStageStatus.FAILED,
                                       progress_percent=100,
                                       message=("확인할 항목: " + ", ".join(missing)) if missing else None))
        return OcrPipelineResult(
            status="COMPLETED" if not missing else "PARTIAL",
            vendor=result.vendor if result else None,
            amount=int(result.amount) if result and result.amount is not None else None,
            transaction_date=result.date if result else None,
            raw_text=result.ocr_raw if result else None,
            missing_fields=missing,
            warnings=["일부 항목을 직접 확인하거나 입력해 주세요."] if missing else [],
            retention_status="under_review",
            pipeline_name="clova_compat",
            pipeline_version="1",
        )


def load_pipeline(spec: str | None) -> OcrPipeline:
    """Load trusted ``module:factory`` server configuration or current CLOVA adapter."""

    if not spec:
        return ClovaPipelineAdapter()
    module_name, separator, factory_name = spec.partition(":")
    if not separator or not module_name or not factory_name:
        raise ValueError("OCR_PIPELINE은 'module:factory' 형식이어야 합니다.")
    factory = getattr(importlib.import_module(module_name), factory_name)
    pipeline = factory()
    if not callable(getattr(pipeline, "process", None)):
        raise TypeError("OCR 어댑터는 process(request, report_progress) 메서드를 제공해야 합니다.")
    return pipeline
