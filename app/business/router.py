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


from app.business.models import BusinessProfile
from app.business.schemas import OperatingProfileUpdate
from app.common.exceptions import AppException
from app.transactions.models import Transaction

@v2_router.get('/profile')
def operating_profile(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    b=session.exec(select(BusinessProfile).where(BusinessProfile.user_id==user.id)).first()
    p=session.exec(select(TaxProfileV2).where(TaxProfileV2.user_id==user.id)).first()
    return {'business_name':b.business_name if b else None,'business_number':b.business_number if b else None,
        'verified_tax_type':b.tax_type if b else None,'verification_status':b.verification_status if b else 'unverified',
        'declared_tax_type':p.tax_type if p else None,'entity_type':p.entity_type if p else None,
        'operating_industry':p.operating_industry if p else None,'business_description':p.business_description if p else None,
        'has_employees':p.has_employees if p else None,'onboarding_completed':bool(p and p.onboarding_completed)}

@v2_router.put('/profile')
def save_operating_profile(body: OperatingProfileUpdate,user: User = Depends(get_current_user),session: Session = Depends(get_session)):
    p=session.exec(select(TaxProfileV2).where(TaxProfileV2.user_id==user.id)).first() or TaxProfileV2(user_id=user.id)
    if body.entity_type=='corporation' and body.declared_tax_type=='simplified':
        raise AppException(400,'INVALID_TAX_TYPE','법인은 일반과세 유형을 확인해 주세요.')
    p.tax_type=body.declared_tax_type;p.entity_type=body.entity_type;p.operating_industry=body.operating_industry
    p.business_description=body.business_description.strip() if body.business_description else None;p.has_employees=body.has_employees
    p.industry_category='food_service' if body.operating_industry in ('food_service','cafe') else 'manufacturing' if body.operating_industry=='manufacturing' else 'other' if body.operating_industry else None
    p.onboarding_completed=all(x is not None for x in (p.tax_type,p.entity_type,p.operating_industry,p.business_description,p.has_employees)) and bool(p.business_description)
    p.confirmed_at=None
    b=session.exec(select(BusinessProfile).where(BusinessProfile.user_id==user.id)).first()
    if b and body.business_name is not None:b.business_name=body.business_name.strip();session.add(b)
    for t in session.exec(select(Transaction).where(Transaction.user_id==user.id,Transaction.direction=='purchase',Transaction.deleted_at.is_(None))).all():
        t.review_status='stale';t.deductible_vat=0;t.risk_level=None;t.analysis_reason='사업 프로필이 변경되어 다시 확인해야 합니다.';t.revision+=1;session.add(t)
    session.add(p);session.commit()
    return operating_profile(user,session)
