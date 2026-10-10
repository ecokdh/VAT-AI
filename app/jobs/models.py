import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class AsyncJob(SQLModel, table=True):
    __tablename__ = "async_jobs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)
    job_type: str = Field(nullable=False, index=True)  # ocr | pdf
    payload_json: str = Field(nullable=False)
    status: str = Field(default="PENDING", nullable=False, index=True)
    result_json: Optional[str] = Field(default=None)
    error_code: Optional[str] = Field(default=None)
    error_message: Optional[str] = Field(default=None)
    attempts: int = Field(default=0, nullable=False)
    max_attempts: int = Field(default=3, nullable=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)
    started_at: Optional[datetime] = Field(default=None)
    finished_at: Optional[datetime] = Field(default=None)
