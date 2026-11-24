"""분류 그래프 노드. 외부 호출(검색·LLM)은 graph.py에서 주입받아 테스트에서 교체할 수 있게 한다."""

import logging
from collections.abc import Callable

from app.deduction.analyzer import AnalysisRequest, LegalReference
from app.deduction.graph.rules import CATEGORIES, match_rule
from app.deduction.graph.state import ClassificationResult, DeductionState, JudgeOutput
from app.deduction.rag.schemas import LawOut


Retriever = Callable[[str, list[int]], list[LawOut]]  # (검색어, 제외할 조문 id)
CoreLaws = Callable[[], list[LawOut]]
JudgeLLM = Callable[[AnalysisRequest, list[LawOut], list[str]], JudgeOutput]
SlmJudge = Callable[[AnalysisRequest, list[LawOut]], tuple[JudgeOutput, float | None]]  # (판정, 신뢰도)

MAX_ATTEMPTS = 3  # 최초 1회 + 재시도 2회
# 골드셋 평가(training/deduction)에서 신뢰도 0.9 이상인 sLLM 확정 판정은 정확도 97%, 오공제 0건이었다.
SLM_MIN_CONFIDENCE = 0.9
# 오판 영향이 크거나 sLLM이 틀린 유형(경차·승합차)이 있는 분류는 sLLM이 확신해도 LLM이 판정한다.
SLM_HIGH_RISK_CATEGORIES = {"차량유지비", "기업업무추진비"}

logger = logging.getLogger(__name__)


def normalize(state: DeductionState) -> DeductionState:
    # 필수 값(거래일·금액)은 AnalysisRequest 계약이 이미 검증한다.
    tx = state["request"].transaction
    query = f"{tx.vendor} {tx.description} {(tx.ocr_text or '')[:500]}".strip()
    return {"query": query, "errors": [], "attempts": 0}


def rule_check(state: DeductionState) -> DeductionState:
    rule = match_rule(state["request"].transaction)
    if rule is None:
        return {}

    result = ClassificationResult(
        verdict=rule.verdict,
        category=rule.category,
        reason=rule.reason,
        legal_references=[rule.reference],
        judged_by="rule",
    )
    return {"result": result}


def retrieve_laws(state: DeductionState, retrieve: Retriever, core_laws: CoreLaws) -> DeductionState:
    # 핵심 조문은 항상 넣고, 검색은 그 밖의 조문으로 채운다.
    core = core_laws()
    laws = core + retrieve(state["query"], [law.id for law in core])
    if not laws:
        return {"laws": [], "errors": ["검색된 법령 조문이 없습니다."]}

    return {"laws": laws}


def slm_judge(state: DeductionState, slm: SlmJudge) -> DeductionState:
    """sLLM이 먼저 판정하고, 아래 조건에 걸리면 판정을 버리고 LLM(judge)으로 넘긴다."""
    try:
        judgement, confidence = slm(state["request"], state["laws"])
    except Exception as exc:  # 서버가 꺼져 있거나 응답이 깨졌으면 LLM이 판정한다.
        reason = f"sLLM 호출 실패: {type(exc).__name__}"
    else:
        reason = escalation_reason(judgement, confidence, {law.id for law in state["laws"]})
        if reason is None:
            return {"judgement": judgement, "judged_by": "slm"}

    logger.info("공제 판정을 LLM으로 넘김: %s", reason)
    return {"route_reason": reason}


def escalation_reason(judgement: JudgeOutput, confidence: float | None, law_ids: set[int]) -> str | None:
    if errors := validate(judgement, law_ids):
        return "sLLM 출력 검증 실패: " + "; ".join(errors)
    if judgement.verdict == "ambiguous":
        return "애매 판정"
    if confidence is None or confidence < SLM_MIN_CONFIDENCE:
        return f"신뢰도 낮음({confidence})"
    if judgement.category in SLM_HIGH_RISK_CATEGORIES:
        return f"고위험 분류({judgement.category})"
    return None


def judge(state: DeductionState, judge_llm: JudgeLLM) -> DeductionState:
    attempts = state["attempts"] + 1
    try:
        judgement = judge_llm(state["request"], state["laws"], state["errors"])
    except Exception as exc:
        return {"judgement": None, "errors": [f"LLM 호출 실패: {exc}"], "attempts": attempts}

    return {"judgement": judgement, "attempts": attempts, "judged_by": "llm"}


def verify(state: DeductionState) -> DeductionState:
    judgement = state["judgement"]
    if judgement is None:
        return {"errors": state["errors"]}

    return {"errors": validate(judgement, {law.id for law in state["laws"]})}


def validate(judgement: JudgeOutput, law_ids: set[int]) -> list[str]:
    errors = []

    if judgement.category not in CATEGORIES:
        errors.append(f"category '{judgement.category}'는 허용된 분류가 아닙니다.")
    if not judgement.reason.strip():
        errors.append("reason이 비어 있습니다.")

    cited = set(judgement.cited_law_ids)
    for case in judgement.cases:
        cited |= set(case.cited_law_ids)
    if unknown := cited - law_ids:
        errors.append(f"조문 목록에 없는 id를 인용했습니다: {sorted(unknown)}")

    if judgement.verdict != "ambiguous":
        if not judgement.cited_law_ids:
            errors.append("근거 조문 id(cited_law_ids)가 비어 있습니다.")
        return errors

    if not (judgement.decision_point or "").strip():
        errors.append("ambiguous인데 decision_point가 비어 있습니다.")
    if {case.result for case in judgement.cases} != {"deductible", "non_deductible"}:
        errors.append("ambiguous인데 cases에 공제와 불공제 결과가 모두 있지 않습니다.")
    for case in judgement.cases:
        if not case.reason.strip() or not case.cited_law_ids:
            errors.append(f"case '{case.condition}'에 사유 또는 근거 조문이 없습니다.")

    return errors


def finalize(state: DeductionState) -> DeductionState:
    judgement = state["judgement"]
    ambiguous = judgement.verdict == "ambiguous"
    cases = judgement.cases if ambiguous else []

    cited = set(judgement.cited_law_ids)
    for case in cases:
        cited |= set(case.cited_law_ids)

    result = ClassificationResult(
        verdict=judgement.verdict,
        category=judgement.category,
        reason=judgement.reason,
        decision_point=judgement.decision_point if ambiguous else None,
        cases=cases,
        legal_references=[to_reference(law) for law in state["laws"] if law.id in cited],
        judged_by=state["judged_by"],
        route_reason=state.get("route_reason"),
    )
    return {"result": result}


def mark_failed(state: DeductionState) -> DeductionState:
    result = ClassificationResult(verdict="failed", error_message="; ".join(state["errors"]),
                                  route_reason=state.get("route_reason"))
    return {"result": result}


def to_reference(law: LawOut) -> LegalReference:
    return LegalReference(source_id=str(law.id), title=law.source, locator=law.article)
