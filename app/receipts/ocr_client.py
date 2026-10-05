"""Naver CLOVA OCR 어댑터 (Template V2, Document OCR, General OCR 및 Fallback 지원)."""

import base64
from dataclasses import dataclass, replace
from datetime import date as date_
from decimal import Decimal, InvalidOperation
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
import time
from typing import Any, Optional
import uuid

import httpx

from app.core.config import settings
from app.receipts.kie import boxes_from_fields, fill_from_boxes, financial_from_fields


@dataclass(frozen=True)
class PartialRead:
    """필수 칸이 빠져도 읽은 값만 담는다. 성공 완료가 아니다."""

    vendor: str | None
    amount: float | None
    date: date_ | None
    ocr_raw: str
    business_number: str | None = None
    supply_amount: float | None = None
    vat_amount: float | None = None
    items: tuple[str, ...] = ()
    text_boxes: tuple[dict, ...] = ()
    taxable_supply_amount: float | None = None
    tax_exempt_amount: float | None = None
    transaction_amount: float | None = None
    payment_amount: float | None = None
    subtotal_amount: float | None = None
    item_amounts: tuple[dict, ...] = ()
    line_items: tuple[dict, ...] = ()
    review_reasons: tuple[str, ...] = ()
    raw_response: dict | None = None
    document: dict | None = None
    money_evidence: dict | None = None

    def useful(self) -> bool:
        return bool(
            (self.vendor and self.vendor.strip())
            or self.amount is not None
            or self.date is not None
            or self.business_number
            or self.items
            or (self.ocr_raw and self.ocr_raw.strip())
        )


@dataclass(frozen=True)
class OcrResult:
    vendor: str
    amount: float
    date: date_
    ocr_raw: str
    business_number: str | None = None
    supply_amount: float | None = None
    vat_amount: float | None = None
    items: tuple[str, ...] = ()
    text_boxes: tuple[dict, ...] = ()
    taxable_supply_amount: float | None = None
    tax_exempt_amount: float | None = None
    transaction_amount: float | None = None
    payment_amount: float | None = None
    subtotal_amount: float | None = None
    item_amounts: tuple[dict, ...] = ()
    line_items: tuple[dict, ...] = ()
    review_reasons: tuple[str, ...] = ()
    raw_response: dict | None = None
    document: dict | None = None
    money_evidence: dict | None = None


VENDOR_FIELDS = ("상호명", "상호", "가맹점명", "상점명", "store_name")
# amount는 합계/총 결제금액만 매핑한다. 공급가액은 총액으로 쓰지 않는다.
AMOUNT_FIELDS = ("총금액", "총액", "결제금액", "합계", "total_amount", "total")
DATE_FIELDS = ("거래일자", "거래일", "작성일자", "transaction_date", "date")
BUSINESS_NUMBER_FIELDS = ("사업자등록번호", "사업자번호", "사업자 번호", "business_number")
SUPPLY_FIELDS = ("공급가액", "공급가", "supply_amount")
VAT_FIELDS = ("부가세", "부가가치세", "부가가치세액", "vat", "VAT")
ITEM_FIELDS = ("품목", "상품명", "품명", "item")
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
    parsed = float(amount)
    return parsed if math.isfinite(parsed) else None


def _parse_business_number(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) != 10:
        return None
    return digits


def _item_texts(fields: list[dict[str, Any]]) -> tuple[str, ...]:
    items: list[str] = []
    for field in fields:
        if field.get("name") not in ITEM_FIELDS:
            continue
        value = field.get("inferText")
        if isinstance(value, str) and value.strip():
            items.append(value.strip())
    return tuple(items)


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


def _parse_text_lines(text: str) -> Optional[OcrResult]:
    """일반 텍스트 또는 비정형 OCR 텍스트에서 상호명, 금액, 거래일자를 추출."""
    if not text or not text.strip():
        return None

    # 상호명 추출: 키워드 접두사 우선
    vm = re.search(
        r"(?:상호명|상호|가맹점명|상점명)\s*[:：]?\s*([^\s\n\r]+(?:\s+[^\s\n\r]+)*?)(?=\s*(?:거래일자|거래일|작성일자|일자|총금액|총액|결제금액|합계|부가세|\n|$))",
        text,
    )
    vendor = vm.group(1).strip() if vm else None

    # 거래일자 추출
    dm = re.search(r"(?:거래일자|거래일|작성일자|일자)\s*[:：]?\s*([0-9\-/.\s]+)", text)
    tx_date = _parse_date(dm.group(1)) if dm else _parse_date(text)

    # 금액 추출: 합계/총금액 키워드
    am = re.search(r"(?:총금액|총액|결제금액|합계)[ \t]*[:：]?[ \t]*([0-9,]+(?:\.\d+)?)", text)
    amount = _parse_amount(am.group(1)) if am else None

    # 키워드 접두사가 없을 때의 상호명 fallback: 영수증 최상단 유효 라인
    if not vendor:
        for line in text.splitlines():
            line = line.strip()
            if not line or any(
                kw in line
                for kw in ["영수증", "거래일", "총금액", "합계", "부가세", "카드", "승인", "신용", "매출"]
            ):
                continue
            vendor = line
            break

    # 금액 fallback: 합계 관련 토큰 인근의 숫자
    if amount is None:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for index, line in enumerate(lines):
            if not any(keyword in line for keyword in ("합계", "총액", "총금액", "결제금액")):
                continue
            if index + 1 >= len(lines):
                continue
            nxt = lines[index + 1]
            if re.fullmatch(r"\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?", nxt):
                amount = _parse_amount(nxt)
                break

    if not vendor or amount is None or tx_date is None:
        return None

    return OcrResult(
        vendor=vendor,
        amount=amount,
        date=tx_date,
        ocr_raw=text.strip(),
    )


def parse_response(payload: object) -> Optional[OcrResult]:
    """CLOVA OCR 응답(Template OCR V2, Document OCR 영수증, General OCR)을 통합 파싱."""
    if not isinstance(payload, dict):
        return None
    images = payload.get("images")
    if not isinstance(images, list) or not images or not isinstance(images[0], dict):
        return None
    image = images[0]

    # 실패 응답은 필드가 있어도 성공으로 치지 않는다.
    if str(image.get("inferResult", "SUCCESS")).upper() == "FAILURE":
        return None

    # 1. Document OCR 영수증 규격 (receipt.result)
    receipt_node = image.get("receipt", {})
    if not isinstance(receipt_node, dict):
        receipt_data = None
    else:
        receipt_data = receipt_node.get("result")
    if isinstance(receipt_data, dict):
        store_info = receipt_data.get("storeInfo") or {}
        if not isinstance(store_info, dict):
            store_info = {}
        vendor = (
            store_info.get("name", {}).get("text")
            or store_info.get("subName", {}).get("text")
        )
        total_price = receipt_data.get("totalPrice") or {}
        if not isinstance(total_price, dict):
            total_price = {}
        amount = _parse_amount(total_price.get("price", {}).get("text"))
        payment_info = receipt_data.get("paymentInfo") or {}
        if not isinstance(payment_info, dict):
            payment_info = {}
        tx_date = _parse_date(payment_info.get("date", {}).get("text"))
        raw_parts = [str(vendor or ""), str(amount or ""), str(tx_date or "")]
        raw_text = "\n".join([p for p in raw_parts if p])
        if vendor and amount is not None and tx_date is not None:
            biz = store_info.get("bizNum", {})
            business_number = _parse_business_number(
                biz.get("text") if isinstance(biz, dict) else None
            )
            sub_total = receipt_data.get("subTotal", {})
            tax = receipt_data.get("tax", {})
            supply_amount = _parse_amount(
                sub_total.get("price", {}).get("text") if isinstance(sub_total, dict) else None
            )
            vat_amount = _parse_amount(
                tax.get("price", {}).get("text") if isinstance(tax, dict) else None
            )
            items: list[str] = []
            raw_items = receipt_data.get("items")
            if isinstance(raw_items, list):
                for item in raw_items:
                    if not isinstance(item, dict):
                        continue
                    name = item.get("name", {})
                    text = name.get("text") if isinstance(name, dict) else None
                    if isinstance(text, str) and text.strip():
                        items.append(text.strip())
            return OcrResult(
                vendor=vendor.strip(),
                amount=amount,
                date=tx_date,
                ocr_raw=raw_text,
                business_number=business_number,
                supply_amount=supply_amount,
                vat_amount=vat_amount,
                items=tuple(items),
                transaction_amount=amount,
            )

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

    # 2. Template OCR V2 규격 (템플릿 필드명이 매핑된 경우)
    has_template_names = any(
        f.get("name")
        in (
            VENDOR_FIELDS
            + AMOUNT_FIELDS
            + DATE_FIELDS
            + SUPPLY_FIELDS
            + BUSINESS_NUMBER_FIELDS
            + VAT_FIELDS
        )
        for f in typed_fields
    )
    boxes = boxes_from_fields(typed_fields)

    if has_template_names:
        current = {
            "vendor": _field_text(typed_fields, VENDOR_FIELDS),
            "amount": _parse_amount(_field_text(typed_fields, AMOUNT_FIELDS)),
            "date": _parse_date(_field_text(typed_fields, DATE_FIELDS)),
            "business_number": _parse_business_number(
                _field_text(typed_fields, BUSINESS_NUMBER_FIELDS)
            ),
            "supply_amount": _parse_amount(_field_text(typed_fields, SUPPLY_FIELDS)),
            "vat_amount": _parse_amount(_field_text(typed_fields, VAT_FIELDS)),
            "items": _item_texts(typed_fields),
        }
        current.update(financial_from_fields(typed_fields))
        filled = fill_from_boxes(current, boxes)
        return _result_from_filled(filled, raw_text)

    if raw_text:
        parsed = _parse_text_lines(raw_text)
        current = {
            "vendor": parsed.vendor if parsed else None,
            "amount": parsed.amount if parsed else None,
            "date": parsed.date if parsed else None,
            "business_number": parsed.business_number if parsed else None,
            "supply_amount": parsed.supply_amount if parsed else None,
            "vat_amount": parsed.vat_amount if parsed else None,
            "items": parsed.items if parsed else (),
        }
        current.update(financial_from_fields(typed_fields))
        filled = fill_from_boxes(current, boxes)
        return _result_from_filled(filled, raw_text)

    return None


def collect_partial(payload: object) -> PartialRead | None:
    """실패 응답이나 일부 칸만 있어도 읽은 값만 돌려준다. 예외는 내지 않는다."""
    if not isinstance(payload, dict):
        return None
    images = payload.get("images")
    if not isinstance(images, list) or not images or not isinstance(images[0], dict):
        return None
    image = images[0]
    fields = image.get("fields")
    typed_fields = [field for field in fields if isinstance(field, dict)] if isinstance(fields, list) else []
    raw_lines = [
        field["inferText"].strip()
        for field in typed_fields
        if isinstance(field.get("inferText"), str) and field["inferText"].strip()
    ]
    boxes = boxes_from_fields(typed_fields)
    current = {
        "vendor": _field_text(typed_fields, VENDOR_FIELDS),
        "amount": _parse_amount(_field_text(typed_fields, AMOUNT_FIELDS)),
        "date": _parse_date(_field_text(typed_fields, DATE_FIELDS)),
        "business_number": _parse_business_number(_field_text(typed_fields, BUSINESS_NUMBER_FIELDS)),
        "supply_amount": _parse_amount(_field_text(typed_fields, SUPPLY_FIELDS)),
        "vat_amount": _parse_amount(_field_text(typed_fields, VAT_FIELDS)),
        "items": _item_texts(typed_fields),
    }
    current.update(financial_from_fields(typed_fields))
    filled = fill_from_boxes(current, boxes)
    vendor = filled.get("vendor")
    raw_text = "\n".join(raw_lines)
    partial = PartialRead(
        vendor=vendor.strip() if isinstance(vendor, str) and vendor.strip() else None,
        amount=filled.get("amount"),
        date=filled.get("date"),
        ocr_raw=raw_text,
        business_number=filled.get("business_number"),
        supply_amount=filled.get("supply_amount"),
        vat_amount=filled.get("vat_amount"),
        items=tuple(filled.get("items") or ()),
        text_boxes=tuple(filled.get("text_boxes") or ()),
        line_items=tuple(filled.get("line_items") or ()),
        review_reasons=tuple(filled.get("review_reasons") or ()),
        document=filled.get("document"),
        money_evidence=filled.get("money_evidence"),
        **{field: filled.get(field) for field in ("taxable_supply_amount", "tax_exempt_amount", "transaction_amount", "payment_amount", "subtotal_amount")},
    )
    return partial if partial.useful() else None


def _result_from_filled(filled: dict, raw_text: str) -> OcrResult | None:
    vendor = filled.get("vendor")
    amount = filled.get("amount")
    date = filled.get("date")
    if not raw_text or not vendor or amount is None or date is None:
        return None
    boxes = filled.get("text_boxes") or []
    return OcrResult(
        vendor=vendor,
        amount=amount,
        date=date,
        ocr_raw=raw_text,
        business_number=filled.get("business_number"),
        supply_amount=filled.get("supply_amount"),
        vat_amount=filled.get("vat_amount"),
        items=tuple(filled.get("items") or ()),
        text_boxes=tuple(boxes),
        line_items=tuple(filled.get("line_items") or ()),
        review_reasons=tuple(filled.get("review_reasons") or ()),
        document=filled.get("document"),
        money_evidence=filled.get("money_evidence"),
        **{field: filled.get(field) for field in ("taxable_supply_amount", "tax_exempt_amount", "transaction_amount", "payment_amount", "subtotal_amount")},
    )


def _format_for_mime_type(mime_type: str) -> tuple[str, str] | None:
    formats = {
        "image/jpeg": ("jpg", "jpg"),
        "image/png": ("png", "png"),
    }
    return formats.get(mime_type)


def _extract_fallback(image_bytes: bytes) -> Optional[OcrResult]:
    """CLOVA 템플릿 미매칭(NOT_FOUND) 또는 장애 시 로컬/Windows OCR을 통한 안전한 fallback 추출."""
    if not image_bytes or len(image_bytes) < 500:
        return None
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(image_bytes)
        tmp_name = f.name
    try:
        ps_script = f"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine, Windows.Media.Ocr, ContentType = WindowsRuntime] | Out-Null
$fileTask = [Windows.Storage.StorageFile]::GetFileFromPathAsync('{tmp_name}')
$asTaskGeneric = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {{ $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.IsGenericMethod }} | Select-Object -First 1
$file = $asTaskGeneric.MakeGenericMethod([Windows.Storage.StorageFile]).Invoke($null, @($fileTask)).GetAwaiter().GetResult()
$stream = $asTaskGeneric.MakeGenericMethod([Windows.Storage.Streams.IRandomAccessStream]).Invoke($null, @($file.OpenAsync([Windows.Storage.FileAccessMode]::Read))).GetAwaiter().GetResult()
$decoder = $asTaskGeneric.MakeGenericMethod([Windows.Graphics.Imaging.BitmapDecoder]).Invoke($null, @([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream))).GetAwaiter().GetResult()
$bitmap = $asTaskGeneric.MakeGenericMethod([Windows.Graphics.Imaging.SoftwareBitmap]).Invoke($null, @($decoder.GetSoftwareBitmapAsync())).GetAwaiter().GetResult()
$koLang = [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | Where-Object {{ $_.LanguageTag -eq 'ko' }}
$engine = if ($koLang) {{ [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($koLang) }} else {{ [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }}
$result = $asTaskGeneric.MakeGenericMethod([Windows.Media.Ocr.OcrResult]).Invoke($null, @($engine.RecognizeAsync($bitmap))).GetAwaiter().GetResult()
$b64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($result.Text))
Write-Output $b64
"""
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        b64 = res.stdout.strip()
        if not b64:
            return None
        raw_text = base64.b64decode(b64).decode("utf-8")
        return _parse_text_lines(raw_text)
    except Exception:
        return None
    finally:
        Path(tmp_name).unlink(missing_ok=True)


async def extract_receipt(
    image_bytes: bytes, mime_type: str = "image/jpeg"
) -> OcrResult | PartialRead | None:
    api_url = settings.CLOVA_OCR_API_URL.strip()
    secret_key = (settings.CLOVA_OCR_SECRET_KEY or settings.CLOVA_API_KEY).strip()
    format_info = _format_for_mime_type(mime_type)
    if not api_url or not secret_key or format_info is None:
        return _extract_fallback(image_bytes)

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
        if 200 <= response.status_code < 300:
            payload = response.json()
            parsed = parse_response(payload)
            if parsed is not None:
                return replace(parsed, raw_response=payload)
            partial = collect_partial(payload)
            if partial is not None:
                return replace(partial, raw_response=payload)
        return _extract_fallback(image_bytes)
    except (
        httpx.TimeoutException,
        httpx.RequestError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
    ):
        return _extract_fallback(image_bytes)
