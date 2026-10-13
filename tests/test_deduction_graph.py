import uuid
from datetime import date

import pytest

from app.analysis.contract import AnalysisRequest, BusinessFacts, TransactionFacts
from app.deduction.graph.adapter import AnalysisFailedError, LangGraphAnalyzer
from app.deduction.graph.graph import build_graph, classify
from app.deduction.graph.prompts import build_input
from app.deduction.graph.state import JudgeCase, JudgeOutput
from app.deduction.rag.schemas import LawOut


LAWS = [
    LawOut(id=1, source="부가가치세법", article="제38조", content="공제하는 매입세액"),
    LawOut(id=2, source="부가가치세법", article="제39조", content="공제하지 아니하는 매입세액"),
    LawOut(id=3, source="부가가치세법", article="제26조", content="재화 또는 용역의 공급에 대한 면세"),
]


def request(**kwargs) -> AnalysisRequest:
    transaction = {
        "transaction_id": 1,
        "revision": 1,
        "transaction_date": date(2026, 9, 14),
        "vendor": "한빛문구",
        "description": "사무용품",
        "purpose": None,
        "ocr_text": "A4 용지, 토너",
        "direction": "purchase",
        "evidence_type": "card",
        "business_related": None,
        "total_amount": 88000,
        "supply_amount": 80000,
        "vat_amount": 8000,
        "tax_treatment": "taxable",
        "deemed_input_supply": 0,
        "deemed_input_eligible": None,
        "deemed_input_document_type": None,
    }
    return AnalysisRequest(
        run_id=uuid.uuid4(),
        transaction=TransactionFacts(**{**transaction, **kwargs}),
        business=BusinessFacts(),
    )


def deductible(cited=(1,), category="소모품비", reason="사업용 소모품 구입") -> JudgeOutput:
    return JudgeOutput(
        verdict="deductible",
        category=category,
        reason=reason,
        cited_law_ids=list(cited),
        decision_point=None,
        cases=[],
    )


def ambiguous(cases) -> JudgeOutput:
    return JudgeOutput(
        verdict="ambiguous",
        category="복리후생비",
        reason="식사 목적에 따라 공제 여부가 달라집니다.",
        cited_law_ids=[],
        decision_point="이 식사가 사업 관련 지출인지, 개인 식사인지",
        cases=cases,
    )


BUSINESS = JudgeCase(condition="직원 회식", result="deductible", reason="사업 관련 지출", cited_law_ids=[1])
PRIVATE = JudgeCase(condition="개인 식사", result="non_deductible", reason="사업과 무관", cited_law_ids=[2])


class FakeJudge:
    """미리 정한 출력을 차례로 돌려주고, 받은 검증 오류를 기록한다."""

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.received_errors = []

    def __call__(self, request, laws, errors):
        self.received_errors.append(list(errors))
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output


def graph_with(judge, laws=LAWS, core=()):
    retrieved = []

    def retrieve(query, exclude_ids):
        retrieved.append((query, exclude_ids))
        return [law for law in laws if law.id not in exclude_ids]

    return build_graph(retrieve, lambda: list(core), judge), retrieved


def run(judge, laws=LAWS, core=(), **transaction_kwargs):
    graph, retrieved = graph_with(judge, laws, core)
    return classify(graph, request(**transaction_kwargs)), retrieved


def test_rule_match_skips_retrieval_and_llm():
    judge = FakeJudge()
    result, retrieved = run(judge, vendor="강남 유흥주점")

    assert result.verdict == "non_deductible"
    assert result.category == "유흥비"
    assert result.legal_references
    assert retrieved == [] and judge.received_errors == []


@pytest.mark.parametrize(
    "kwargs",
    [{"supply_amount": 0, "vat_amount": 0}, {"tax_treatment": "exempt", "vat_amount": None}],
)
def test_no_vat_transaction_is_non_deductible_without_llm(kwargs):
    judge = FakeJudge()
    result, retrieved = run(judge, vendor="우리마트", description="사과, 콩나물", **kwargs)

    assert result.verdict == "non_deductible"
    assert [ref.locator for ref in result.legal_references] == ["제26조 제1항"]
    assert retrieved == [] and judge.received_errors == []


def test_prompt_includes_vat_amounts_and_industry():
    text = build_input(
        request(vat_amount=None).model_copy(
            update={"business": BusinessFacts(industry_category="소매업", industry_subtype="생활용품")}
        ),
        LAWS,
        [],
    )

    assert "공급가액: 80000" in text
    assert "부가가치세: 영수증에 표시 없음" in text
    assert "업종: 소매업 / 생활용품" in text


def test_deductible_keeps_only_cited_laws():
    result, _ = run(FakeJudge(deductible(cited=[1])))

    assert result.verdict == "deductible"
    assert [ref.source_id for ref in result.legal_references] == ["1"]
    assert result.decision_point is None and result.cases == []


def test_ambiguous_returns_decision_point_and_cases():
    result, _ = run(FakeJudge(ambiguous([BUSINESS, PRIVATE])), vendor="한우마을 고깃집")

    assert result.verdict == "ambiguous"
    assert result.decision_point
    assert {case.result for case in result.cases} == {"deductible", "non_deductible"}
    assert {ref.source_id for ref in result.legal_references} == {"1", "2"}


def test_hallucinated_citation_is_retried_with_errors():
    judge = FakeJudge(deductible(cited=[99]), deductible(cited=[1]))
    result, _ = run(judge)

    assert result.verdict == "deductible"
    assert judge.received_errors[0] == []
    assert "99" in judge.received_errors[1][0]


@pytest.mark.parametrize(
    "bad_output",
    [
        deductible(cited=[]),
        deductible(category="아무거나"),
        deductible(reason=" "),
        ambiguous([BUSINESS]),
        ambiguous([BUSINESS, PRIVATE.model_copy(update={"cited_law_ids": []})]),
    ],
)
def test_invalid_output_fails_after_max_attempts(bad_output):
    judge = FakeJudge(bad_output, bad_output, bad_output)
    result, _ = run(judge)

    assert result.verdict == "failed"
    assert result.error_message
    assert len(judge.received_errors) == 3


def test_llm_exception_is_retried():
    result, _ = run(FakeJudge(RuntimeError("timeout"), deductible()))

    assert result.verdict == "deductible"


def test_no_laws_found_fails():
    judge = FakeJudge()
    result, _ = run(judge, laws=[])

    assert result.verdict == "failed"
    assert judge.received_errors == []


def test_core_laws_always_passed_and_excluded_from_search():
    received_laws = []

    def judge(request, laws, errors):
        received_laws.append([law.id for law in laws])
        return deductible(cited=[2])

    result, retrieved = run(judge, core=LAWS[1:2])

    assert retrieved[0][1] == [2]
    assert received_laws == [[2, 1, 3]]
    assert result.verdict == "deductible"


def test_core_laws_alone_are_enough_when_search_finds_nothing():
    result, _ = run(FakeJudge(deductible(cited=[2])), laws=[], core=LAWS[1:2])

    assert result.verdict == "deductible"


def test_adapter_maps_deductible_to_contract():
    graph, _ = graph_with(FakeJudge(deductible(cited=[1])))
    decision = LangGraphAnalyzer(graph).analyze(request())

    assert decision.disposition == "DEDUCTIBLE"
    assert decision.reason == "사업용 소모품 구입"
    assert decision.legal_references[0].locator == "제38조"


def test_adapter_maps_ambiguous_to_needs_review_with_cases():
    graph, _ = graph_with(FakeJudge(ambiguous([BUSINESS, PRIVATE])))
    decision = LangGraphAnalyzer(graph).analyze(request(vendor="한우마을 고깃집"))

    assert decision.disposition == "NEEDS_REVIEW"
    assert "확인할 사실: 이 식사가 사업 관련 지출인지, 개인 식사인지" in decision.reason
    assert "- 직원 회식: 공제 — 사업 관련 지출 (근거: 부가가치세법 제38조)" in decision.reason
    assert "- 개인 식사: 불공제 — 사업과 무관 (근거: 부가가치세법 제39조)" in decision.reason


def test_adapter_raises_on_failure_instead_of_needs_review():
    graph, _ = graph_with(FakeJudge(), laws=[])

    with pytest.raises(AnalysisFailedError, match="법령 조문"):
        LangGraphAnalyzer(graph).analyze(request())
