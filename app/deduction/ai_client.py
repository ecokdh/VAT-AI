"""GPT 호출 인터페이스. 이후 RAG 등으로 고도화할 때 이 파일의 구현체만 교체한다."""

from dataclasses import dataclass

from pydantic import BaseModel

from app.common.exceptions import AppError


MODEL_NAME = "gpt-5.6-terra"


@dataclass
class DeductionJudgement:
    is_deductible: bool
    reason: str
    category: str
    amount: float


class _DeductionResponse(BaseModel):
    is_deductible: bool
    reason: str
    category: str


def judge_deduction(vendor: str, amount: float, ocr_raw: str) -> DeductionJudgement:
    """영수증 OCR 결과를 받아 스켈레톤 단계의 공제 가능 여부를 판별한다."""
    try:
        from openai import OpenAI

        from app.core.config import settings

        response = OpenAI(api_key=settings.OPENAI_API_KEY).responses.parse(
            model=MODEL_NAME,
            instructions=(
                "당신은 VAT-AI의 사전 검토 도우미입니다. 제공된 영수증 정보만 사용해 "
                "한국 부가가치세 매입세액 공제 가능성을 간단히 판단하세요. "
                "법률 자문을 단정적으로 제공하지 말고, 정보가 부족하거나 불명확하면 "
                "공제 불가로 두고 reason에 전문가 확인이 필요하다고 쓰세요."
            ),
            input=(
                f"상호명: {vendor or '미상'}\n"
                f"금액: {amount}\n"
                f"OCR 원문: {ocr_raw or '없음'}"
            ),
            text_format=_DeductionResponse,
            store=False,
        )
    except Exception as exc:
        raise AppError(502, "EXTERNAL_API_ERROR", "공제 판별 API 호출에 실패했습니다.") from exc

    result = response.output_parsed
    if result is None:
        raise AppError(502, "EXTERNAL_API_ERROR", "공제 판별 결과를 해석하지 못했습니다.")

    return DeductionJudgement(
        is_deductible=result.is_deductible,
        reason=result.reason,
        category=result.category,
        amount=amount if result.is_deductible else 0.0,
    )