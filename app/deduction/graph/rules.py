"""LLM 없이 확정할 수 있는 판정 규칙, 분류(category) 목록, 항상 참조할 핵심 조문."""

from dataclasses import dataclass

from app.analysis.contract import LegalReference, TransactionFacts


# TODO: 기획서에 확정된 분류 목록이 없어 초안으로 둔다. 팀 확정 후 교체.
CATEGORIES = (
    "원재료",
    "소모품비",
    "복리후생비",
    "차량유지비",
    "통신비",
    "임차료",
    "지급수수료",
    "광고선전비",
    "기업업무추진비",
    "유흥비",
    "개인지출",
    "기타",
)


# 거의 모든 매입 거래의 판단에 쓰이는 조문. 검색 결과와 관계없이 항상 judge에 넘긴다.
CORE_LAWS = (
    ("부가가치세법", "제38조 제1항"),  # 공제하는 매입세액
    ("부가가치세법", "제39조 제1항"),  # 공제하지 아니하는 매입세액
    ("부가가치세법", "제46조 제3항"),  # 신용카드매출전표등 수취분 공제
    ("부가가치세법 시행령", "제77조"),  # 사업과 직접 관련이 없는 지출
    ("부가가치세법 시행령", "제78조"),  # 비영업용 소형승용차 제외 업종
    ("부가가치세법 시행령", "제79조"),  # 기업업무추진비
    ("부가가치세법 시행령", "제88조 제5항"),  # 신용카드매출전표등 공제 제외 업종
)


@dataclass(frozen=True)
class Rule:
    verdict: str
    category: str
    reason: str
    # 워커는 근거 없는 확정 판정을 검토 필요로 돌리므로, 규칙도 근거 조문을 가진다.
    reference: LegalReference
    keywords: tuple[str, ...] = ()


def _law(source: str, locator: str) -> LegalReference:
    return LegalReference(source_id=f"{source} {locator}", title=source, locator=locator)


# 부가가치세가 없는 거래(면세 등)는 공제할 매입세액 자체가 없다.
NO_VAT_RULE = Rule(
    "non_deductible",
    "기타",
    "거래에 부가가치세가 없어(면세 등) 공제할 매입세액이 없습니다. 의제매입세액공제 대상 여부는 별도로 판단합니다.",
    _law("부가가치세법", "제26조 제1항"),
)

# 영수증만으로 결론이 명확한 경우만 둔다. 조금이라도 맥락에 따라 갈리면 LLM 판단으로 넘긴다.
KEYWORD_RULES = (
    Rule(
        "non_deductible",
        "유흥비",
        "유흥업소 지출은 매입세액 불공제 대상입니다.",
        _law("부가가치세법", "제39조 제1항"),
        keywords=("유흥주점", "단란주점", "룸살롱", "나이트클럽"),
    ),
)


def match_rule(tx: TransactionFacts) -> Rule | None:
    if tx.tax_treatment == "exempt" or tx.vat_amount == 0:
        return NO_VAT_RULE

    text = f"{tx.vendor} {tx.description} {tx.ocr_text or ''}"
    return next((rule for rule in KEYWORD_RULES if any(k in text for k in rule.keywords)), None)
