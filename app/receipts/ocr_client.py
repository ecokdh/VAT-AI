"""CLOVA OCR 호출 인터페이스. 이후 성능 개선 시 이 파일의 구현체만 교체한다.

반환 형태는 api-spec.md §2.2 receipts 컬럼 중 OCR 추출분과 맞춘다:
vendor, amount, date, ocr_raw. 실패 시 None을 반환하고 호출부(service.py)가
Receipt.status="failed"로 저장한다.
"""

from dataclasses import dataclass
from datetime import date as date_
from typing import Optional


@dataclass
class OcrResult:
    vendor: str
    amount: float
    date: date_
    ocr_raw: str


def extract_receipt(image_bytes: bytes) -> Optional[OcrResult]:
    raise NotImplementedError  # TODO: CLOVA OCR API 호출, 실패 시 None 반환
