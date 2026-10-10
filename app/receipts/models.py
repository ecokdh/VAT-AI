import uuid
import json
from datetime import date as date_, datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class Receipt(SQLModel, table=True):
    """OCR upload record; legacy sync API still returns done/failed immediately."""

    __tablename__ = "receipts"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)
    image_url: str = Field(nullable=False)
    ocr_raw: Optional[str] = Field(default=None)
    vendor: Optional[str] = Field(default=None)
    amount: Optional[float] = Field(default=None)
    date: Optional[date_] = Field(default=None)
    status: str = Field(nullable=False)  # processing | done | failed
    processing_stage: Optional[str] = Field(default="queued")
    processing_progress: int = Field(default=0, nullable=False)
    stage_statuses_json: str = Field(
        default='{"photo_quality":"pending","text_recognition":"pending","transaction_extraction":"pending","missing_field_check":"pending"}',
        nullable=False,
    )
    ocr_warnings_json: str = Field(default="[]", nullable=False)
    ocr_pipeline_name: Optional[str] = Field(default=None)
    ocr_pipeline_version: Optional[str] = Field(default=None)
    ocr_missing_fields_json: str = Field(default="[]", nullable=False)
    extraction_confirmed: bool = Field(default=False, nullable=False, index=True)
    ocr_user_attempts: int = Field(default=1, nullable=False)
    retention_status: str = Field(default="under_review", nullable=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)

    @property
    def stage_statuses(self) -> dict[str, str]:
        try:
            return json.loads(self.stage_statuses_json)
        except (TypeError, json.JSONDecodeError):
            return {}

    @property
    def ocr_warnings(self) -> list[str]:
        try:
            return json.loads(self.ocr_warnings_json)
        except (TypeError, json.JSONDecodeError):
            return []

    @property
    def ocr_missing_fields(self) -> list[str]:
        try:
            return json.loads(self.ocr_missing_fields_json)
        except (TypeError, json.JSONDecodeError):
            return []

