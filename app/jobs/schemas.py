from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel


class AsyncJobOut(BaseModel):
    id: UUID
    job_type: Literal["ocr", "pdf"]
    status: Literal["PENDING", "PROCESSING", "COMPLETED", "FAILED"]
    result_json: Optional[str]
    error_code: Optional[str]
    error_message: Optional[str]
    attempts: int
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]


class ReceiptJobAccepted(BaseModel):
    job_id: UUID
    receipt_id: int
    status: Literal["PENDING"]
