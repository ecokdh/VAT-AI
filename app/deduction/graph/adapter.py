"""분류 그래프를 PurchaseAnalyzer 계약(app/analysis/contract.py)에 연결하는 어댑터.

연결: DEDUCTION_ANALYZER=app.deduction.graph.adapter:create_analyzer
"""

from sqlmodel import Session

from app.analysis.contract import AnalysisDecision, AnalysisRequest
from app.core.database import engine
from app.deduction.ai_client import judge_with_laws
from app.deduction.graph.graph import build_graph, classify
from app.deduction.graph.rules import CORE_LAWS
from app.deduction.graph.state import ClassificationResult
from app.deduction.rag.schemas import LawOut
from app.deduction.rag.service import get_laws, search_laws


ANALYZER_NAME = "langgraph-deduction"
ANALYZER_VERSION = "0.1.0"
REASON_MAX_LENGTH = 4000  # AnalysisDecision.reason 제한

DISPOSITIONS = {
    "deductible": "DEDUCTIBLE",
    "non_deductible": "NOT_DEDUCTIBLE",
    "ambiguous": "NEEDS_REVIEW",
}
CASE_LABELS = {"deductible": "공제", "non_deductible": "불공제"}


class AnalysisFailedError(RuntimeError):
    """그래프가 판정을 내지 못함. 워커가 분석 작업을 재시도·실패 처리한다."""


class LangGraphAnalyzer:
    def __init__(self, graph):
        self.graph = graph

    def analyze(self, request: AnalysisRequest) -> AnalysisDecision:
        result = classify(self.graph, request)
        # 시스템 실패는 사용자가 판단할 '애매'(NEEDS_REVIEW)로 보내지 않는다.
        if result.verdict == "failed":
            raise AnalysisFailedError(result.error_message or "공제 분류에 실패했습니다.")

        return AnalysisDecision(
            disposition=DISPOSITIONS[result.verdict],
            reason=build_reason(result)[:REASON_MAX_LENGTH],
            legal_references=result.legal_references,
            analyzer_name=ANALYZER_NAME,
            analyzer_version=ANALYZER_VERSION,
        )


def build_reason(result: ClassificationResult) -> str:
    if result.verdict != "ambiguous":
        return result.reason

    locators = {ref.source_id: f"{ref.title} {ref.locator or ''}".strip() for ref in result.legal_references}
    lines = [result.reason, f"확인할 사실: {result.decision_point}"]
    for case in result.cases:
        basis = ", ".join(locators[str(law_id)] for law_id in case.cited_law_ids)
        lines.append(f"- {case.condition}: {CASE_LABELS[case.result]} — {case.reason} (근거: {basis})")
    return "\n".join(lines)


def _retrieve(query: str, exclude_ids: list[int]) -> list[LawOut]:
    with Session(engine) as session:
        return search_laws(session, query, exclude_ids=exclude_ids)


def _core_laws() -> list[LawOut]:
    with Session(engine) as session:
        return get_laws(session, CORE_LAWS)


def create_analyzer() -> LangGraphAnalyzer:
    return LangGraphAnalyzer(build_graph(_retrieve, _core_laws, judge_with_laws))
