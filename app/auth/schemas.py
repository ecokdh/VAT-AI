from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.business.schemas import BusinessProfileOut


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    business_name: str
    business_number: str
    terms_accepted: bool
    privacy_accepted: bool
    marketing_accepted: bool = False


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


class AuthResponse(BaseModel):
    access_token: str
    user: UserOut
