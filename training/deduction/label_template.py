"""무료 라벨링: 기준표(criteria.py)의 정답과 사유 틀로 JudgeOutput을 만든다. API·DB를 전혀 호출하지 않는다.

프롬프트에 넣을 조문 목록은 teacher 라벨링(labeled.jsonl)에서 같은 쟁점의 거래가 실제로 검색했던 목록을 빌려 쓴다.
핵심 조문 7개는 항상 같고, 검색 조문 5개도 같은 쟁점이면 비슷하게 나오기 때문이다.

    python label_template.py --cases data/cases_t.jsonl --laws-from data/labeled.jsonl --out data/labeled_template.jsonl
"""

import argparse
import json
import random
import re
import sys
from pathlib import Path

from criteria import CARD_46, INDUSTRIES, ISSUES

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.deduction.graph.nodes import validate  # noqa: E402
from app.deduction.graph.state import JudgeOutput  # noqa: E402

EVIDENCE = {"card_receipt": "신용카드매출전표", "cash_receipt": "지출증빙용 현금영수증", "tax_invoice": "세금계산서"}
ISSUE = {issue.id: issue for issue in ISSUES}
INDUSTRY_NAME = {(category, subtype): name for category, subtype, name in INDUSTRIES.values()}


def fix_josa(text: str) -> str:
    """'은(는)'을 앞말의 마지막 한글 받침에 맞춰 고른다."""
    def pick(match):
        last = next((c for c in reversed(match.group(1)) if "가" <= c <= "힣"), "가")
        return match.group(1) + ("은" if (ord(last) - ord("가")) % 28 else "는")
    return re.sub(r"(\S+)은\(는\)", pick, text)


def cited(fact, laws: list[dict], evidence: str) -> list[int]:
    refs = list(fact.laws)
    if fact.verdict == "deductible" and evidence != "tax_invoice":
        refs.append(CARD_46)  # 카드·현금영수증 수취분 공제는 제46조 제3항도 근거다.
    index = {f"{law['source']} {law['article']}": law["id"] for law in laws}
    return [index[ref] for ref in dict.fromkeys(refs)]


def judgement(rng: random.Random, case: dict, laws: list[dict]) -> JudgeOutput:
    issue = ISSUE[case["issue"]]
    fact = issue.facts[case["fact"]]
    tx, business = case["request"]["transaction"], case["request"]["business"]
    values = {"items": tx["description"], "evidence": EVIDENCE[tx["evidence_type"]],
              "industry": INDUSTRY_NAME[business["industry_category"], business["industry_subtype"]]}

    def say(f, reasons=None):
        return fix_josa(rng.choice(reasons or f.reasons).format(**values))

    cases = []
    if fact.verdict == "ambiguous":
        # 사용자가 이미 확인한 사실(business_related)과 어긋나는 경우는 경우별 결과에서 뺀다.
        pool = [f for f in issue.facts
                if f.verdict != "ambiguous" and fact.business_related in (None, f.business_related)]
        # 가정하는 경우라 "확인되었습니다" 같은 확정 문장은 쓰지 않는다.
        cases = [{"condition": f.condition, "result": f.verdict,
                  "reason": say(f, [r for r in f.reasons if "확인" not in r]),
                  "cited_law_ids": cited(f, laws, tx["evidence_type"])} for f in pool]

    return JudgeOutput(
        verdict=fact.verdict,
        category=fact.category,
        reason=say(fact),
        cited_law_ids=cited(fact, laws, tx["evidence_type"]),
        decision_point=(fact.decision_point or issue.decision_point) if fact.verdict == "ambiguous" else None,
        cases=cases,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--laws-from", type=Path, required=True, help="teacher 라벨 파일(조문 목록을 빌려 옴)")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    rng = random.Random(args.seed)

    law_pool = {}
    for row in map(json.loads, open(args.laws_from, encoding="utf-8")):
        if row.get("laws"):
            law_pool.setdefault(row["issue"], []).append(row["laws"])

    rows = []
    for case in map(json.loads, open(args.cases, encoding="utf-8")):
        laws = rng.choice(law_pool[case["issue"]])
        output = judgement(rng, case, laws)
        if errors := validate(output, {law["id"] for law in laws}):  # 앱 verify 노드와 같은 검사
            raise ValueError(f"{case['id']}: {errors}")
        rows.append({**case, "teacher": "template", "laws": laws, "judgement": output.model_dump(),
                     "verdict": output.verdict, "attempts": 0, "agree": True})

    with open(args.out, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    print(f"{len(rows)}건 → {args.out}")


if __name__ == "__main__":
    main()
