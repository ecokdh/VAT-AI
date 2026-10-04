import re

from app.common.exceptions import AppException
from app.business import nts_client
from app.business.schemas import BusinessVerifyResponse


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
