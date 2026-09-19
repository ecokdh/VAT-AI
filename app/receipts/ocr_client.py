"""Naver CLOVA Template OCR V2 어댑터.

현재 파서는 기존 프로젝트 문서가 지정한 Custom API V2 중, 배포된 Template의
필드명(`fields[].name`)을 사용하는 계약만 읽는다. General OCR의 일반 텍스트
응답이나 Document OCR 영수증 응답을 이 어댑터가 성공으로 오인하지 않는다.
"""

from dataclasses import dataclass
from datetime import date as date_
from decimal import Decimal, InvalidOperation
import json
import re
import time
import uuid
from typing import Any, Optional

import httpx

from app.core.config import settings


@dataclass(frozen=True)
class OcrResult:
    vendor: str
    amount: float
    date: date_
    ocr_raw: str


VENDOR_FIELDS = ("상호명", "상호", "가맹점명", "상점명", "store_name")
# amount는 현재 api-spec.md의 합계/총 결제금액만 매핑한다. 공급가액은 매핑하지 않는다.
AMOUNT_FIELDS = ("총금액", "총액", "결제금액", "합계", "total_amount", "total")
DATE_FIELDS = ("거래일자", "거래일", "작성일자", "transaction_date", "date")
OCR_CONTRACT = "template_v2"


def _field_text(fields: list[dict[str, Any]], names: tuple[str, ...]) -> str | None:
    for field in fields:
        if not isinstance(field, dict) or field.get("name") not in names:
            continue
        value = field.get("inferText")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _parse_amount(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(r"-?\d[\d,]*(?:\.\d+)?", value.replace(" ", ""))
    if match is None:
        return None
    try:
        amount = Decimal(match.group(0).replace(",", ""))
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return float(amount)


def _parse_date(value: str | None) -> date_ | None:
    if not value:
        return None
    match = re.search(r"(20\d{2})\D+(\d{1,2})\D+(\d{1,2})", value)
    if match is None:
        return None
    try:
        return date_(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def parse_response(payload: object) -> Optional[OcrResult]:
    if not isinstance(payload, dict):
        return None
    images = payload.get("images")
    if not isinstance(images, list) or not images or not isinstance(images[0], dict):
        return None
    image = images[0]
    if image.get("inferResult") != "SUCCESS":
        return None
    fields = image.get("fields")
    if not isinstance(fields, list):
        return None

    typed_fields = [field for field in fields if isinstance(field, dict)]
    raw_lines = [
        field["inferText"].strip()
        for field in typed_fields
        if isinstance(field.get("inferText"), str) and field["inferText"].strip()
    ]
    raw_text = "\n".join(raw_lines)
    vendor = _field_text(typed_fields, VENDOR_FIELDS)
    amount = _parse_amount(_field_text(typed_fields, AMOUNT_FIELDS))
    transaction_date = _parse_date(_field_text(typed_fields, DATE_FIELDS))

    # 현재 API 계약은 필수 추출값이 모두 있어야 done이다. 부분 결과를
    # 세무 데이터처럼 저장하지 않고 failed로 남긴다.
    if not raw_text or not vendor or amount is None or transaction_date is None:
        return None
    return OcrResult(
        vendor=vendor,
        amount=amount,
        date=transaction_date,
        ocr_raw=raw_text,
    )


def _format_for_mime_type(mime_type: str) -> tuple[str, str] | None:
    formats = {
        "image/jpeg": ("jpg", "jpg"),
        "image/png": ("png", "png"),
    }
    return formats.get(mime_type)


async def extract_receipt(
    image_bytes: bytes, mime_type: str = "image/jpeg"
) -> Optional[OcrResult]:
    api_url = settings.CLOVA_OCR_API_URL.strip()
    secret_key = (settings.CLOVA_OCR_SECRET_KEY or settings.CLOVA_API_KEY).strip()
    format_info = _format_for_mime_type(mime_type)
    if not api_url or not secret_key or format_info is None:
        return None

    image_format, extension = format_info
    message = {
        "version": "V2",
        "requestId": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "lang": "ko",
        "images": [{"format": image_format, "name": "receipt"}],
    }
    files = {
        "file": (f"receipt.{extension}", image_bytes, mime_type),
    }
    try:
        async with httpx.AsyncClient(timeout=settings.CLOVA_TIMEOUT_SECONDS) as client:
            response = await client.post(
                api_url,
                headers={"X-OCR-SECRET": secret_key},
                data={"message": json.dumps(message, ensure_ascii=False)},
                files=files,
            )
        if not 200 <= response.status_code < 300:
            return None
        return parse_response(response.json())
    except (
        httpx.TimeoutException,
        httpx.RequestError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
    ):
        return None
