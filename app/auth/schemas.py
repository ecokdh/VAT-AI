from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator

from app.business.schemas import BusinessFilingInfo, BusinessProfileOut, TaxProfileUpdate


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    nickname: str | None = Field(default=None, min_length=2, max_length=20)
    business_name: str
    business_number: str
    age_confirmed: bool  # 만 14세 이상
    terms_accepted: bool
    privacy_accepted: bool
    overseas_transfer_accepted: bool  # 개인정보 국외 이전(OpenAI)
    ai_notice_accepted: bool  # 공제 판별은 AI 예측이라는 안내 확인
    sample_pdf_notice_accepted: bool  # 신고서 PDF는 예시라 제출하면 안 된다는 안내 확인
    marketing_accepted: bool = False
    tax_profile: TaxProfileUpdate | None = None
    filing_info: BusinessFilingInfo | None = None

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


class PasswordResetCodeVerification(BaseModel):
    request_id: UUID
    code: str = Field(pattern=r"^[0-9]{6}$")
