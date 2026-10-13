"""공제 분류 그래프 조립.

normalize → rule_check ─(규칙 확정)→ END
              └→ retrieve_laws(핵심 조문 + 검색) ─(조문 없음)→ mark_failed
                    └→ judge → verify ─(통과)→ finalize
                         ↑        ├(실패, 재시도 가능)→ judge
                         └────────┘(재시도 초과)→ mark_failed
"""

from functools import partial

from langgraph.graph import END, START, StateGraph

from app.analysis.contract import AnalysisRequest
from app.deduction.graph import nodes
from app.deduction.graph.nodes import MAX_ATTEMPTS, CoreLaws, JudgeLLM, Retriever
from app.deduction.graph.state import ClassificationResult, DeductionState


def build_graph(retrieve: Retriever, core_laws: CoreLaws, judge_llm: JudgeLLM):
    graph = StateGraph(DeductionState)

    graph.add_node("normalize", nodes.normalize)
    graph.add_node("rule_check", nodes.rule_check)
    graph.add_node("retrieve_laws", partial(nodes.retrieve_laws, retrieve=retrieve, core_laws=core_laws))
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
        "retrieve_laws", lambda s: "judge" if s["laws"] else "mark_failed"
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
