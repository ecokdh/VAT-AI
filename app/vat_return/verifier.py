"""만든 신고서를 학습한 모델(Qwen3-VL LoRA)로 다시 읽어 칸별로 대조한다.

모델은 서버(training/serve.py)에서 돌고, 여기서는 이미지를 보내 읽은 값만 받는다.
FORM_VERIFIER_URL이 비어 있거나 서버가 응답하지 않아도 PDF 생성은 막지 않는다.
모델도 틀릴 수 있으므로(검증 데이터 기준 신고서 1장 전체 일치 87.5%) 결과는 '확인 권장' 경고로만 쓴다.
"""
from typing import Protocol

import httpx

from app.core.config import settings
from app.vat_return.fields import EXCEPTION_FIELDS, FIELD_BY_ID


class FormReader(Protocol):
    def read(self, image_png: bytes) -> dict[str, str]: ...


class RemoteFormReader:
    def __init__(self, url: str, timeout: float):
        self.url, self.timeout = url.rstrip("/"), timeout

    def read(self, image_png: bytes) -> dict[str, str]:
        response = httpx.post(f"{self.url}/read", files={"image": ("page1.png", image_png, "image/png")}, timeout=self.timeout)
        response.raise_for_status()
        values = response.json().get("values")
        if not isinstance(values, dict):
            raise ValueError("검증 서버 응답에 values가 없습니다.")
        return {str(k): str(v) for k, v in values.items()}


def load_reader() -> FormReader | None:
    url = settings.FORM_VERIFIER_URL
    return RemoteFormReader(url, settings.FORM_VERIFIER_TIMEOUT_SECONDS) if url else None


def compare(expected: dict[str, str], read: dict[str, str]) -> list[dict]:
    """넣으려던 값과 모델이 읽은 값이 다른 칸. 모르는 필드 ID와 '예외' 칸은 무시한다."""
    keys = [k for k in FIELD_BY_ID if (k in expected or k in read) and k not in EXCEPTION_FIELDS]
    return [{"field": k, "label": FIELD_BY_ID[k].label, "expected": expected.get(k, ""), "read": read.get(k, "")}
            for k in keys if expected.get(k, "") != read.get(k, "")]


def verify(expected: dict[str, str], image_png: bytes, reader: FormReader | None) -> dict:
    if reader is None:
        return {"status": "skipped", "message": "검증 서버가 설정되지 않아 모델 검증을 건너뛰었습니다."}
    try:
        mismatches = compare(expected, reader.read(image_png))
    except (httpx.HTTPError, ValueError) as exc:
        return {"status": "error", "message": f"검증 서버에 연결하지 못해 모델 검증을 건너뛰었습니다. ({type(exc).__name__})"}
    if not mismatches:
        return {"status": "passed", "message": "모델이 다시 읽은 값이 모든 칸에서 일치합니다."}
    return {"status": "mismatch", "mismatches": mismatches,
            "message": f"모델이 다시 읽은 값이 {len(mismatches)}개 칸에서 다릅니다. 해당 칸을 직접 확인해 주세요."}
