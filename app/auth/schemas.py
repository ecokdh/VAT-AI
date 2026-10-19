from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator

from app.business.schemas import BusinessProfileOut, TaxProfileUpdate


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    nickname: str | None = Field(default=None, min_length=2, max_length=20)
    business_name: str
    business_number: str
    terms_accepted: bool
    privacy_accepted: bool
    marketing_accepted: bool = False
    tax_profile: TaxProfileUpdate | None = None

    @field_validator("nickname", mode="before")
    @classmethod
    def trim_nickname(cls, value):
        return value.strip() if isinstance(value, str) else value


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
    nickname: str | None = None
    created_at: datetime
    business: BusinessProfileOut | None = None
    ocr_guide_seen: bool = False


class AuthResponse(BaseModel):
    access_token: str
    user: UserOut


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nickname: str = Field(min_length=2, max_length=20)

    @field_validator("nickname", mode="before")
    @classmethod
    def trim_nickname(cls, value):
        return value.strip() if isinstance(value, str) else value


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmation(BaseModel):
    token: str = Field(min_length=32, max_length=128)
    password: str = Field(min_length=8, max_length=72)
