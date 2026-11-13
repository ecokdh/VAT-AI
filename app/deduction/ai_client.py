"""공제 판별 LLM 호출. 분류 그래프의 judge 노드가 사용한다."""

from app.deduction.analyzer import AnalysisRequest
from app.deduction.graph import prompts
from app.deduction.graph.state import JudgeOutput
from app.deduction.rag.schemas import LawOut


MODEL_NAME = "gpt-5.6-terra"


def judge_with_laws(
    request: AnalysisRequest, laws: list[LawOut], errors: list[str]
) -> JudgeOutput:
    """분류 그래프 judge 노드의 LLM 호출. 검증(verify)은 그래프가 따로 한다."""
    from openai import OpenAI

    from app.core.config import settings

    response = OpenAI(api_key=settings.OPENAI_API_KEY).responses.parse(
        model=MODEL_NAME,
        instructions=prompts.INSTRUCTIONS,
        input=prompts.build_input(request, laws, errors),
        text_format=JudgeOutput,
        store=False,
    )
    if response.output_parsed is None:
        raise ValueError("판정 결과를 해석하지 못했습니다.")

    return response.output_parsed
