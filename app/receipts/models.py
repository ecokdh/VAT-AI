import uuid
from datetime import date as date_, datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import UniqueConstraint


class Receipt(SQLModel, table=True):
    """receipts 테이블. status는 done | failed | retake."""

    __tablename__ = "receipts"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)
    image_url: str = Field(nullable=False)
    ocr_raw: Optional[str] = Field(default=None)
    vendor: Optional[str] = Field(default=None)
    amount: Optional[float] = Field(default=None)
    date: Optional[date_] = Field(default=None)
    status: str = Field(nullable=False)
    quality_reason: Optional[str] = Field(default=None)
    business_number: Optional[str] = Field(default=None)
    supply_amount: Optional[float] = Field(default=None)
    vat_amount: Optional[float] = Field(default=None)
    taxable_supply_amount: Optional[float] = Field(default=None)
    tax_exempt_amount: Optional[float] = Field(default=None)
    transaction_amount: Optional[float] = Field(default=None)
    payment_amount: Optional[float] = Field(default=None)
    subtotal_amount: Optional[float] = Field(default=None)
    item_amounts_json: Optional[str] = Field(default=None)
    money_schema_version: int = Field(default=1, nullable=False)
    money_sources_json: Optional[str] = Field(default=None)
    items_json: Optional[str] = Field(default=None)
    ocr_original: Optional[str] = Field(default=None)
    confirmed: bool = Field(default=False, nullable=False)
    revision: int = Field(default=1, nullable=False)
    document_json: Optional[str] = Field(default=None)
    ocr_response_json: Optional[str] = Field(default=None)
    file_hash: Optional[str] = Field(default=None, index=True)
    perceptual_hash: Optional[str] = Field(default=None)
    transaction_id: Optional[str] = Field(default=None, foreign_key="transactions.id", index=True)
    line_items: list["LineItem"] = Relationship(sa_relationship_kwargs={"lazy": "selectin"})
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)


class Transaction(SQLModel, table=True):
    __tablename__ = "transactions"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    data_json: str = Field(default="{}")
    revision: int = Field(default=1)
    workflow_status: str = Field(default="NEEDS_CONTEXT")
    original_transaction_id: Optional[str] = Field(default=None, foreign_key="transactions.id")
    adjustment_type: Optional[str] = Field(default=None)


class LineItem(SQLModel, table=True):
    __tablename__ = "line_items"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    receipt_id: int = Field(foreign_key="receipts.id", index=True)
    position: int
    data_json: str


class ReconciliationIssue(SQLModel, table=True):
    __tablename__ = "reconciliation_issues"
    __table_args__ = (UniqueConstraint("receipt_id", "candidate_receipt_id", name="uq_reconciliation_receipt_pair"),)
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    receipt_id: int = Field(foreign_key="receipts.id")
    candidate_receipt_id: int = Field(foreign_key="receipts.id")
    reason: str
    resolved: bool = Field(default=False)
    active: bool = Field(default=True, nullable=False)
    action: Optional[str] = None

