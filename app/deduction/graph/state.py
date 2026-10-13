"""공제 분류 그래프의 입출력과 상태 정의."""

from typing import Literal, TypedDict

from pydantic import BaseModel

from app.analysis.contract import AnalysisRequest, LegalReference
from app.deduction.rag.schemas import LawOut


# failed는 AI/시스템 실패다. 사용자가 판단해야 하는 ambiguous와 섞지 않는다.
Verdict = Literal["deductible", "non_deductible", "ambiguous", "failed"]


class JudgeCase(BaseModel):
    """애매 판정에서 사용자가 답할 사실(decision_point)의 한 경우."""

    condition: str
    result: Literal["deductible", "non_deductible"]
    reason: str
    cited_law_ids: list[int]


class JudgeOutput(BaseModel):
    """judge 노드(LLM) 출력. 애매일 때만 decision_point와 cases를 채운다."""

    verdict: Literal["deductible", "non_deductible", "ambiguous"]
    category: str
    reason: str
    cited_law_ids: list[int]
    decision_point: str | None
    cases: list[JudgeCase]


class ClassificationResult(BaseModel):
    verdict: Verdict
    category: str | None = None
    reason: str | None = None
    decision_point: str | None = None
    cases: list[JudgeCase] = []
    legal_references: list[LegalReference] = []
    error_message: str | None = None


class DeductionState(TypedDict, total=False):
    request: AnalysisRequest
    query: str
    laws: list[LawOut]
    judgement: JudgeOutput | None
    errors: list[str]
    attempts: int
    result: ClassificationResult
