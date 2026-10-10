import json

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.business import service
from app.business.models import TaxProfileV2
from app.business.schemas import BusinessVerifyRequest, BusinessVerifyResponse, TaxProfileOut, TaxProfileUpdate
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.database import get_session

router = APIRouter(prefix="/business", tags=["business"])
v2_router = APIRouter(prefix="/v2/business", tags=["business-v2"])


@router.post("/verify", response_model=BusinessVerifyResponse)
def verify_business(data: BusinessVerifyRequest):
    return service.verify_business(data.business_number)


def _profile_out(item: TaxProfileV2 | None):
    if item is None:
        return TaxProfileOut(
            entity_type=None, industry_category=None, industry_subtype=None, is_sme=None, simplified_industry_rate=None,
            taxable_sales_h1=None, taxable_sales_h2=None,
            deemed_related_taxable_sales_h1=None, deemed_related_taxable_sales_h2=None,
            business_start_date=None,
            business_end_date=None, suspension_periods=[], tax_type_change_date=None,
            changed_to_tax_type=None, confirmed=False, confirmed_at=None,
        )
    return TaxProfileOut(
        entity_type=item.entity_type, industry_category=item.industry_category,
        industry_subtype=item.industry_subtype, is_sme=item.is_sme, simplified_industry_rate=item.simplified_industry_rate,
        taxable_sales_h1=item.taxable_sales_h1, taxable_sales_h2=item.taxable_sales_h2,
        deemed_related_taxable_sales_h1=item.deemed_related_taxable_sales_h1,
        deemed_related_taxable_sales_h2=item.deemed_related_taxable_sales_h2,
        business_start_date=item.business_start_date, business_end_date=item.business_end_date,
        suspension_periods=json.loads(item.suspension_periods_json),
        tax_type_change_date=item.tax_type_change_date,
        changed_to_tax_type=item.changed_to_tax_type,
        confirmed=item.confirmed_at is not None, confirmed_at=item.confirmed_at,
    )


@v2_router.get("/tax-profile", response_model=TaxProfileOut)
def get_tax_profile(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    item = session.exec(select(TaxProfileV2).where(TaxProfileV2.user_id == user.id)).first()
    return _profile_out(item)


@v2_router.put("/tax-profile", response_model=TaxProfileOut)
def put_tax_profile(
    body: TaxProfileUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return _profile_out(service.save_tax_profile(session, user.id, body))
