import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class BusinessProfile(SQLModel, table=True):
    __tablename__ = "business_profiles"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", unique=True, nullable=False)
    business_number: str = Field(nullable=False, max_length=10)
    business_name: Optional[str] = Field(default=None)
    business_status: Optional[str] = Field(default=None)
    business_status_code: Optional[str] = Field(default=None)
    tax_type: Optional[str] = Field(default=None)
    tax_type_code: Optional[str] = Field(default=None)
    end_date: Optional[str] = Field(default=None)
    verification_status: str = Field(default="unverified", nullable=False)
    verified_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)


class TaxProfileV2(SQLModel, table=True):
    """User-confirmed facts required by v2 deterministic tax rules."""

    __tablename__ = "tax_profiles_v2"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", unique=True, nullable=False, index=True)
    entity_type: Optional[str] = Field(default=None)  # individual | corporation
    industry_category: Optional[str] = Field(default=None)  # food_service | manufacturing | other
    industry_subtype: Optional[str] = Field(default=None)
    is_sme: Optional[bool] = Field(default=None)
    simplified_industry_rate: Optional[int] = Field(default=None)
    taxable_sales_h1: Optional[int] = Field(default=None)
    taxable_sales_h2: Optional[int] = Field(default=None)
    deemed_related_taxable_sales_h1: Optional[int] = Field(default=None)
    deemed_related_taxable_sales_h2: Optional[int] = Field(default=None)
    business_start_date: Optional[date] = Field(default=None)
    business_end_date: Optional[date] = Field(default=None)
    suspension_periods_json: str = Field(default="[]", nullable=False)
    tax_type_change_date: Optional[date] = Field(default=None)
    changed_to_tax_type: Optional[str] = Field(default=None)
    confirmed_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)
