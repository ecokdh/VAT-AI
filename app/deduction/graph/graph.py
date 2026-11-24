"""공제 분류 그래프 조립.

normalize → rule_check ─(규칙 확정)→ END
              └→ retrieve_laws(핵심 조문 + 검색) ─(조문 없음)→ mark_failed
                    └→ slm_judge ─(통과·확정·신뢰도 충분·저위험)→ finalize
                         └(애매·신뢰도 낮음·고위험 분류·검증 실패·서버 오류)→ judge
                    judge → verify ─(통과)→ finalize
                     ↑        ├(실패, 재시도 가능)→ judge
                     └────────┘(재시도 초과)→ mark_failed

sLLM이 설정되지 않으면(slm_judge=None) retrieve_laws 다음에 바로 judge(LLM)로 간다.
"""

from functools import partial

from langgraph.graph import END, START, StateGraph

from app.deduction.analyzer import AnalysisRequest
from app.deduction.graph import nodes
from app.deduction.graph.nodes import MAX_ATTEMPTS, CoreLaws, JudgeLLM, Retriever, SlmJudge
from app.deduction.graph.state import ClassificationResult, DeductionState


def build_graph(retrieve: Retriever, core_laws: CoreLaws, judge_llm: JudgeLLM, slm_judge: SlmJudge | None = None):
    graph = StateGraph(DeductionState)
    first_judge = "slm_judge" if slm_judge else "judge"

    graph.add_node("normalize", nodes.normalize)
    graph.add_node("rule_check", nodes.rule_check)
    graph.add_node("retrieve_laws", partial(nodes.retrieve_laws, retrieve=retrieve, core_laws=core_laws))
    if slm_judge:
        graph.add_node("slm_judge", partial(nodes.slm_judge, slm=slm_judge))
    graph.add_node("judge", partial(nodes.judge, judge_llm=judge_llm))
    graph.add_node("verify", nodes.verify)
    graph.add_node("finalize", nodes.finalize)
    graph.add_node("mark_failed", nodes.mark_failed)

    graph.add_edge(START, "normalize")
    graph.add_edge("normalize", "rule_check")
    graph.add_conditional_edges(
        "rule_check", lambda s: END if s.get("result") else "retrieve_laws"
    )
    graph.add_conditional_edges(
        "retrieve_laws", lambda s: first_judge if s["laws"] else "mark_failed"
    )
    if slm_judge:
        graph.add_conditional_edges(
            "slm_judge", lambda s: "finalize" if s.get("judged_by") == "slm" else "judge"
        )
    graph.add_edge("judge", "verify")
    graph.add_conditional_edges("verify", _after_verify)
    graph.add_edge("finalize", END)
    graph.add_edge("mark_failed", END)

    return graph.compile()


def _after_verify(state: DeductionState) -> str:
    if not state["errors"]:
        return "finalize"
    return "judge" if state["attempts"] < MAX_ATTEMPTS else "mark_failed"


def classify(graph, request: AnalysisRequest) -> ClassificationResult:
    return graph.invoke({"request": request})["result"]
