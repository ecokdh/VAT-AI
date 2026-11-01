import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

class MonthlySalesDocument(SQLModel, table=True):
    __tablename__ = 'monthly_sales_documents'
    __table_args__ = (UniqueConstraint('user_id', 'image_sha256', name='uq_monthly_sales_user_image'),)
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key='users.id', nullable=False, index=True)
    image_key: str = Field(nullable=False)
    image_mime: str = Field(nullable=False)
    image_sha256: str = Field(nullable=False, max_length=64)
    raw_prediction_json: str = Field(nullable=False)
    review_json: str = Field(nullable=False)
    ocr_json: str = Field(nullable=False)
    model_response_json: str = Field(nullable=False)
    contract_version: str = Field(nullable=False)
    status: str = Field(default='needs_review', nullable=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)
