import uuid
from datetime import datetime
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
