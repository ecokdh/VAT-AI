"""judge 노드 프롬프트."""

from app.analysis.contract import AnalysisRequest
from app.deduction.graph.rules import CATEGORIES
from app.deduction.rag.schemas import LawOut


INSTRUCTIONS = f"""당신은 한국 부가가치세 매입세액 공제 여부를 분류하는 도우미입니다.

규칙:
1. 반드시 [조문 목록]에 있는 조문만 근거로 판단하고, 인용은 그 조문의 id로만 하세요. 목록에 없는 법령·조문을 지어내지 마세요.
2. verdict:
   - deductible: 거래 정보만으로 매입세액 공제 대상임이 분명함
   - non_deductible: 거래 정보만으로 불공제 대상임이 분명함
   - ambiguous: 사업자 본인만 아는 사실(사업 관련 여부, 사용 목적, 접대 여부 등)에 따라 결론이 갈림
3. [거래]에 사용자가 확인한 사업 관련 여부나 사용 목적이 있으면 그 사실을 전제로 판단하고, 같은 사실을 다시 묻는 ambiguous로 답하지 마세요. [사업자]의 업종처럼 이미 주어진 정보도 다시 묻지 마세요.
4. 신용카드매출전표등 수령명세서 제출, 증빙 보관 같은 신고·보관 절차 요건은 충족된 것으로 보고, ambiguous 사유로 삼지 마세요. ambiguous는 이 거래의 사실관계가 불분명할 때만 씁니다.
5. reason: 판단 사유를 사용자가 이해할 수 있게 한두 문장으로 쓰세요.
6. ambiguous일 때:
   - decision_point: 사용자가 답해야 할 사실을 한 문장으로 쓰세요. (예: "이 식사가 직원 회식 등 사업 관련 지출인지, 개인 식사인지")
   - cases: 그 사실의 경우별 결과를 쓰세요. 공제(deductible)와 불공제(non_deductible) 결과가 모두 있어야 하며, 각 경우에 사유와 근거 조문 id를 쓰세요.
7. deductible/non_deductible일 때는 decision_point를 null, cases를 빈 배열로 두고 cited_law_ids에 근거 조문 id를 쓰세요.
8. category는 다음 중 하나만 사용하세요: {", ".join(CATEGORIES)}
9. [이전 검증 오류]가 있으면 그 오류를 고쳐서 다시 답하세요."""


def build_input(request: AnalysisRequest, laws: list[LawOut], errors: list[str]) -> str:
    tx, business = request.transaction, request.business
    business_related = {True: "예", False: "아니오", None: "미확인"}[tx.business_related]
    industry = " / ".join(filter(None, [business.industry_category, business.industry_subtype]))
    law_lines = "\n\n".join(
        f"[id={law.id}] {law.source} {law.article or ''}\n{law.content}" for law in laws
    )
    parts = [
        "[사업자]",
        f"과세 유형: {business.tax_type or '미확인'}",
        f"업종: {industry or '미확인'}",
        "",
        "[거래]",
        f"거래처: {tx.vendor or '미상'}",
        f"내용: {tx.description or '없음'}",
        f"거래일: {tx.transaction_date}",
        f"합계 금액: {tx.total_amount}",
        f"공급가액: {_amount(tx.supply_amount)}",
        f"부가가치세: {_amount(tx.vat_amount)}",
        f"증빙 유형: {tx.evidence_type}",
        f"사업 관련 여부(사용자 확인): {business_related}",
        f"사용 목적(사용자 입력): {tx.purpose or '없음'}",
        f"OCR 원문: {tx.ocr_text or '없음'}",
        "",
        "[조문 목록]",
        law_lines,
    ]
    if errors:
        parts += ["", "[이전 검증 오류]", *errors]

    return "\n".join(parts)


def _amount(value: int | None) -> str:
    return "영수증에 표시 없음" if value is None else str(value)
