from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.business.schemas import BusinessProfileOut


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    business_name: str
    business_number: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: EmailStr
    name: str
    created_at: datetime
    business: BusinessProfileOut | None = None


class AuthResponse(BaseModel):
    access_token: str
    user: UserOut
