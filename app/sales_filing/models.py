import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class SalesFilingWorkflow(SQLModel, table=True):
    """One auditable, idempotent sales-reconciliation case per user and filing period."""

    __tablename__ = "sales_filing_workflows"
    __table_args__ = (UniqueConstraint("user_id", "period", name="uq_sales_filing_user_period"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)
    period: str = Field(nullable=False, max_length=16)
    business_number: str = Field(default="", nullable=False, max_length=10)
    status: str = Field(default="검토 필요", nullable=False, max_length=24)
    source_checks_json: str = Field(default="{}", nullable=False)
    manual_inputs_json: str = Field(default="[]", nullable=False)
    feedback_json: str = Field(default="[]", nullable=False)
    aggregate_json: str = Field(default="{}", nullable=False)
    issues_json: str = Field(default="[]", nullable=False)
    history_json: str = Field(default="[]", nullable=False)
    input_fingerprint: str = Field(default="", nullable=False, max_length=64)
    revision: int = Field(default=1, nullable=False)
    reconfirmation_required: bool = Field(default=False, nullable=False)
    finalized_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)
