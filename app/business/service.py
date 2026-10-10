import re
import json
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.common.exceptions import AppException
from app.business import nts_client
from app.business.schemas import BusinessVerifyResponse
from app.business.models import TaxProfileV2
from app.business.schemas import TaxProfileUpdate


def normalize_business_number(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9\s-]+", value):
        raise AppException(400, "VALIDATION_ERROR", "사업자번호 형식이 올바르지 않습니다.")

    normalized = re.sub(r"[\s-]", "", value)
    if not re.fullmatch(r"[0-9]{10}", normalized):
        raise AppException(400, "VALIDATION_ERROR", "사업자번호는 숫자 10자리여야 합니다.")
    return normalized


def verify_business(value: str) -> BusinessVerifyResponse:
    business_number = normalize_business_number(value)
    result = nts_client.lookup_status(business_number)
    return BusinessVerifyResponse(
        business_number=business_number,
        business_status=result["b_stt"],
        business_status_code=result["b_stt_cd"],
        tax_type=result["tax_type"],
        tax_type_code=result["tax_type_cd"],
        end_date=result["end_dt"] or None,
        verified=True,
    )


def save_tax_profile(session: Session, user_id, data: TaxProfileUpdate) -> TaxProfileV2:
    payload = data.model_dump(exclude_unset=True, exclude={"confirmed"})
    suspension_periods = payload.pop("suspension_periods", None)
    item = session.exec(select(TaxProfileV2).where(TaxProfileV2.user_id == user_id)).first()
    if item is None:
        item = TaxProfileV2(user_id=user_id)
    for key, value in payload.items():
        setattr(item, key, value)
    if suspension_periods is not None:
        normalized = [period.model_dump(mode="json") for period in data.suspension_periods or []]
        for period in data.suspension_periods or []:
            if period.end_date < period.start_date:
                raise AppException(400, "VALIDATION_ERROR", "휴업 종료일은 시작일보다 빠를 수 없습니다.")
        item.suspension_periods_json = json.dumps(normalized, ensure_ascii=False)
    if item.business_start_date and item.business_end_date and item.business_end_date < item.business_start_date:
        raise AppException(400, "VALIDATION_ERROR", "폐업일은 개업일보다 빠를 수 없습니다.")
    if data.confirmed:
        if item.entity_type not in {"individual", "corporation"}:
            raise AppException(400, "TAX_PROFILE_INCOMPLETE", "개인·법인 구분을 입력해 주세요.")
        if item.industry_category not in {"food_service", "manufacturing", "other"}:
            raise AppException(400, "TAX_PROFILE_INCOMPLETE", "업종 구분을 입력해 주세요.")
        if item.taxable_sales_h1 is None or item.taxable_sales_h2 is None:
            raise AppException(400, "TAX_PROFILE_INCOMPLETE", "2026년 1기·2기 과세 매출액을 입력해 주세요.")
        if item.business_start_date is None:
            raise AppException(400, "TAX_PROFILE_INCOMPLETE", "개업일을 입력해 주세요.")
        if item.industry_category == "food_service" and item.industry_subtype not in {"restaurant", "taxable_entertainment"}:
            raise AppException(400, "TAX_PROFILE_INCOMPLETE", "음식점업 구분을 확인해 주세요.")
        if item.industry_category == "manufacturing" and item.industry_subtype not in {"specified_mill", "other"}:
            raise AppException(400, "TAX_PROFILE_INCOMPLETE", "제조업 구분을 확인해 주세요.")
        if item.industry_category == "manufacturing" and item.industry_subtype == "other" and item.entity_type == "corporation" and item.is_sme is None:
            raise AppException(400, "TAX_PROFILE_INCOMPLETE", "제조업 법인의 중소기업 해당 여부를 입력해 주세요.")
        if item.tax_type_change_date and not item.changed_to_tax_type:
            raise AppException(400, "TAX_PROFILE_INCOMPLETE", "과세유형 변경일과 변경 후 과세유형을 함께 입력해 주세요.")
        item.confirmed_at = datetime.now(timezone.utc)
    elif data.model_fields_set - {"confirmed"}:
        item.confirmed_at = None
    item.updated_at = datetime.now(timezone.utc)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item
