from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field as PydanticField


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


class SuspensionPeriod(BaseModel):
    start_date: date
    end_date: date


class TaxProfileUpdate(BaseModel):
    entity_type: Optional[Literal["individual", "corporation"]] = None
    industry_category: Optional[Literal["food_service", "manufacturing", "other"]] = None
    industry_subtype: Optional[Literal["restaurant", "taxable_entertainment", "specified_mill", "other"]] = None
    is_sme: Optional[bool] = None
    simplified_industry_rate: Optional[int] = PydanticField(default=None, ge=0)
    taxable_sales_h1: Optional[int] = PydanticField(default=None, ge=0)
    taxable_sales_h2: Optional[int] = PydanticField(default=None, ge=0)
    deemed_related_taxable_sales_h1: Optional[int] = PydanticField(default=None, ge=0)
    deemed_related_taxable_sales_h2: Optional[int] = PydanticField(default=None, ge=0)
    business_start_date: Optional[date] = None
    business_end_date: Optional[date] = None
    suspension_periods: Optional[list[SuspensionPeriod]] = None
    tax_type_change_date: Optional[date] = None
    changed_to_tax_type: Optional[Literal["general", "simplified"]] = None
    confirmed: bool = False


class TaxProfileOut(BaseModel):
    entity_type: Optional[str]
    industry_category: Optional[str]
    industry_subtype: Optional[str]
    is_sme: Optional[bool]
    simplified_industry_rate: Optional[int]
    taxable_sales_h1: Optional[int]
    taxable_sales_h2: Optional[int]
    deemed_related_taxable_sales_h1: Optional[int]
    deemed_related_taxable_sales_h2: Optional[int]
    business_start_date: Optional[date]
    business_end_date: Optional[date]
    suspension_periods: list[SuspensionPeriod]
    tax_type_change_date: Optional[date]
    changed_to_tax_type: Optional[str]
    confirmed: bool
    confirmed_at: Optional[datetime]
