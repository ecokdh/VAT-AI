import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class Transaction(SQLModel, table=True):
    """Versioned user-confirmed transaction; legacy Receipt remains untouched."""

    __tablename__ = "transactions"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)
    receipt_id: Optional[int] = Field(default=None, foreign_key="receipts.id", unique=True)
    direction: str = Field(nullable=False, index=True)  # purchase | sales
    transaction_date: date = Field(nullable=False, index=True)
    vendor: str = Field(nullable=False, max_length=255)
    description: str = Field(default="", nullable=False)
    purpose: Optional[str] = Field(default=None)
    evidence_type: str = Field(default="unknown", nullable=False)
    business_related: Optional[bool] = Field(default=None)
    total_amount: int = Field(nullable=False, ge=0)
    supply_amount: Optional[int] = Field(default=None, ge=0)
    vat_amount: Optional[int] = Field(default=None, ge=0)
    tax_treatment: str = Field(default="unknown", nullable=False)
    state: str = Field(default="draft", nullable=False, index=True)
    state_before_delete: Optional[str] = Field(default=None)
    revision: int = Field(default=1, nullable=False)
    review_status: str = Field(default="not_analyzed", nullable=False, index=True)
    risk_level: Optional[str] = Field(default=None)
    deductible_vat: int = Field(default=0, nullable=False)
    deemed_input_supply: int = Field(default=0, nullable=False)
    deemed_input_eligible: Optional[bool] = Field(default=None)
    deemed_input_document_type: Optional[str] = Field(default=None)
    analysis_reason: Optional[str] = Field(default=None)
    legal_references_json: str = Field(default="[]", nullable=False)
    retention_status: str = Field(default="under_review", nullable=False)
    deleted_at: Optional[datetime] = Field(default=None, index=True)
    permanent_delete_requested_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)


class TransactionRevision(SQLModel, table=True):
    __tablename__ = "transaction_revisions"

    id: Optional[int] = Field(default=None, primary_key=True)
    transaction_id: int = Field(foreign_key="transactions.id", nullable=False, index=True)
    revision: int = Field(nullable=False)
    snapshot_json: str = Field(nullable=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)


class AnalysisRun(SQLModel, table=True):
    __tablename__ = "analysis_runs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)
    transaction_ids_json: str = Field(nullable=False)
    status: str = Field(default="PENDING", nullable=False, index=True)
    result_json: Optional[str] = Field(default=None)
    error_code: Optional[str] = Field(default=None)
    error_message: Optional[str] = Field(default=None)
    attempts: int = Field(default=0, nullable=False)
    max_attempts: int = Field(default=3, nullable=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)
    started_at: Optional[datetime] = Field(default=None)
    finished_at: Optional[datetime] = Field(default=None)
