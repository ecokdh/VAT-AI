from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class BusinessVerifyRequest(BaseModel):
    business_number: str


class BusinessVerifyResponse(BaseModel):
    business_number: str
    business_status: str
    business_status_code: str
    tax_type: str
    tax_type_code: str
    end_date: Optional[str] = None
    verified: bool


class BusinessProfileOut(BaseModel):
    id: str
    user_id: str
    business_number: str
    business_name: Optional[str] = None
    business_status: Optional[str] = None
    business_status_code: Optional[str] = None
    tax_type: Optional[str] = None
    tax_type_code: Optional[str] = None
    end_date: Optional[str] = None
    verification_status: str
    verified_at: Optional[datetime] = None
    created_at: datetime
