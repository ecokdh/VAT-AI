from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.business.schemas import BusinessProfileOut, TaxProfileUpdate


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    business_name: str
    business_number: str
    terms_accepted: bool
    privacy_accepted: bool
    marketing_accepted: bool = False
    tax_profile: TaxProfileUpdate | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class EmailAvailabilityRequest(BaseModel):
    email: EmailStr


class EmailAvailabilityResponse(BaseModel):
    available: bool


class UserOut(BaseModel):
    id: str
    email: EmailStr
    name: str
    created_at: datetime
    business: BusinessProfileOut | None = None
    ocr_guide_seen: bool = False


class AuthResponse(BaseModel):
    access_token: str
    user: UserOut


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmation(BaseModel):
    token: str = Field(min_length=32, max_length=128)
    password: str = Field(min_length=8, max_length=72)
