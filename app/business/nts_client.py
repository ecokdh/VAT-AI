"""National Tax Service business registration status lookup."""

import httpx

from app.common.exceptions import AppException
from app.core.config import settings


STATUS_CODES = {"01": "계속사업자", "02": "휴업자", "03": "폐업자"}
AUTH_ERRORS = {
    "SERVICE_KEY_IS_NULL",
    "PERMISSION_DENIED",
    "SERVICE_ACCESS_DENIED_ERROR",
    "SERVICE_KEY_IS_NOT_REGISTERED_ERROR",
    "DEADLINE_HAS_EXPIRED_ERROR",
}
QUOTA_ERRORS = {
    "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR",
    "LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND_EXCEEDS_ERROR",
}


def _api_error(payload: object) -> AppException | None:
    if not isinstance(payload, dict):
        return None
    name = payload.get("error") or payload.get("errorCode") or payload.get("code")
    if isinstance(name, dict):
        name = name.get("name") or name.get("code")
    if not isinstance(name, str):
        return None
    if name in AUTH_ERRORS:
        return AppException(502, "BUSINESS_API_AUTH_ERROR", "사업자정보 조회 인증에 실패했습니다.")
    if name in QUOTA_ERRORS:
        return AppException(503, "BUSINESS_API_QUOTA_EXCEEDED", "사업자정보 조회 호출 한도를 초과했습니다.")
    return None


def lookup_status(business_number: str) -> dict[str, str]:
    key = settings.NTS_BUSINESS_API_KEY.strip()
    if not key:
        raise AppException(503, "BUSINESS_API_NOT_CONFIGURED", "사업자정보 조회 서비스가 설정되지 않았습니다.")

    try:
        response = httpx.post(
            settings.NTS_BUSINESS_API_URL,
            params={"serviceKey": key},
            json={"b_no": [business_number]},
            headers={"Accept": "application/json"},
            timeout=settings.NTS_BUSINESS_TIMEOUT_SECONDS,
        )
    except httpx.TimeoutException as exc:
        raise AppException(504, "BUSINESS_API_TIMEOUT", "사업자정보 조회 시간이 초과되었습니다.") from exc
    except httpx.RequestError as exc:
        raise AppException(502, "BUSINESS_API_ERROR", "사업자정보 조회 서비스에 연결할 수 없습니다.") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        if response.is_success:
            raise AppException(502, "BUSINESS_API_INVALID_RESPONSE", "사업자정보 조회 응답이 올바르지 않습니다.") from exc
        raise AppException(502, "BUSINESS_API_ERROR", "사업자정보 조회에 실패했습니다.") from exc

    error = _api_error(payload)
    if error is not None:
        raise error
    if not response.is_success:
        raise AppException(502, "BUSINESS_API_ERROR", "사업자정보 조회에 실패했습니다.")
    if not isinstance(payload, dict) or payload.get("status_code") != "OK":
        raise AppException(502, "BUSINESS_API_INVALID_RESPONSE", "사업자정보 조회 응답이 올바르지 않습니다.")

    data = payload.get("data")
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
        raise AppException(502, "BUSINESS_API_INVALID_RESPONSE", "사업자정보 조회 응답이 올바르지 않습니다.")
    row = data[0]
    if row.get("b_no") != business_number:
        raise AppException(502, "BUSINESS_API_INVALID_RESPONSE", "사업자정보 조회 응답이 올바르지 않습니다.")

    status = row.get("b_stt")
    status_code = row.get("b_stt_cd")
    if status == "" and status_code == "":
        raise AppException(404, "BUSINESS_NOT_REGISTERED", "등록된 사업자정보를 찾을 수 없습니다.")
    if status_code not in STATUS_CODES or status != STATUS_CODES[status_code]:
        raise AppException(502, "BUSINESS_API_INVALID_RESPONSE", "사업자정보 조회 응답이 올바르지 않습니다.")
    for field in ("tax_type", "tax_type_cd", "end_dt"):
        if not isinstance(row.get(field), str):
            raise AppException(502, "BUSINESS_API_INVALID_RESPONSE", "사업자정보 조회 응답이 올바르지 않습니다.")
    return row
