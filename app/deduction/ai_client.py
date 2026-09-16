"""GPT 호출 인터페이스. 이후 RAG 등으로 고도화할 때 이 파일의 구현체만 교체한다.

반환 형태는 api-spec.md §3.3 POST /receipts/{id}/analyze 응답 필드와 맞춘다.
"""

from dataclasses import dataclass


@dataclass
class DeductionJudgement:
    is_deductible: bool
    reason: str
    category: str
    amount: float


def judge_deduction(vendor: str, amount: float, ocr_raw: str) -> DeductionJudgement:
    raise NotImplementedError
    # TODO: OpenAI API 단순 호출. 실패 시 AppError(502, "EXTERNAL_API_ERROR", ...)
