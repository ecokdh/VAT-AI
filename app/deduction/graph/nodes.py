"""분류 그래프 노드. 외부 호출(검색·LLM)은 graph.py에서 주입받아 테스트에서 교체할 수 있게 한다."""

from collections.abc import Callable

from app.analysis.contract import AnalysisRequest, LegalReference
from app.deduction.graph.rules import CATEGORIES, match_rule
from app.deduction.graph.state import ClassificationResult, DeductionState, JudgeOutput
from app.deduction.rag.schemas import LawOut


Retriever = Callable[[str, list[int]], list[LawOut]]  # (검색어, 제외할 조문 id)
CoreLaws = Callable[[], list[LawOut]]
JudgeLLM = Callable[[AnalysisRequest, list[LawOut], list[str]], JudgeOutput]

MAX_ATTEMPTS = 3  # 최초 1회 + 재시도 2회


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
    )
    return {"result": result}


def retrieve_laws(state: DeductionState, retrieve: Retriever, core_laws: CoreLaws) -> DeductionState:
    # 핵심 조문은 항상 넣고, 검색은 그 밖의 조문으로 채운다.
    core = core_laws()
    laws = core + retrieve(state["query"], [law.id for law in core])
    if not laws:
        return {"laws": [], "errors": ["검색된 법령 조문이 없습니다."]}

    return {"laws": laws}


def judge(state: DeductionState, judge_llm: JudgeLLM) -> DeductionState:
    attempts = state["attempts"] + 1
    try:
        judgement = judge_llm(state["request"], state["laws"], state["errors"])
    except Exception as exc:
        return {"judgement": None, "errors": [f"LLM 호출 실패: {exc}"], "attempts": attempts}

    return {"judgement": judgement, "attempts": attempts}


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
    )
    return {"result": result}


def mark_failed(state: DeductionState) -> DeductionState:
    result = ClassificationResult(verdict="failed", error_message="; ".join(state["errors"]))
    return {"result": result}


def to_reference(law: LawOut) -> LegalReference:
    return LegalReference(source_id=str(law.id), title=law.source, locator=law.article)
