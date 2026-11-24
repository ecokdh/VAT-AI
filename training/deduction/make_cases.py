"""판정 기준표(criteria.py)로 합성 거래를, gold.py로 골드셋을 만든다. GPU·DB 불필요.

    python make_cases.py --groups 8 --out data/cases.jsonl
    python make_cases.py --gold --out data/gold.jsonl

한 줄 = 앱의 AnalysisRequest(run_id 제외)와 기준표 정답(expected).
같은 영수증에서 사용 목적만 바꾼 변형은 같은 group으로 묶어 train/val을 나눌 때 함께 움직인다.
"""

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

from criteria import INDUSTRIES, ISSUES
from gold import GOLD

PAYMENT = {"card_receipt": "신용카드", "cash_receipt": "현금영수증(지출증빙)", "tax_invoice": "계좌이체"}


def business_number(rng: random.Random) -> str:
    return f"{rng.randint(100, 899)}-{rng.randint(10, 99)}-{rng.randint(10000, 99999)}"


def build_request(rng, industry, vendor, items, evidence, purpose, related, day):
    """items: [(품목, 수량, 단가)] — 단가는 부가세 포함."""
    total = sum(qty * price for _, qty, price in items)
    supply = round(total / 1.1)
    vat = total - supply
    names = ", ".join(name for name, _, _ in items)
    lines = ", ".join(f"{name} x{qty} {qty * price}" for name, qty, price in items)
    ocr = "\n".join([
        f"상호: {vendor}",
        f"사업자번호: {business_number(rng)}",
        f"거래일시: {day.isoformat()} {rng.randint(9, 21):02d}:{rng.randint(0, 59):02d}",
        f"결제수단: {PAYMENT[evidence]}",
        "과세유형(영수증 표기): 과세",
        f"공급가액: {supply} / 부가세: {vat} / 결제금액: {total}",
        f"품목: {lines}",
    ])
    category, subtype, _ = INDUSTRIES[industry]
    return {
        "contract_version": "v1",
        "transaction": {
            "transaction_id": 1, "revision": 1, "transaction_date": day.isoformat(),
            "vendor": vendor, "description": names, "purpose": purpose, "ocr_text": ocr,
            "direction": "purchase", "evidence_type": evidence, "business_related": related,
            "total_amount": total, "supply_amount": supply, "vat_amount": vat, "tax_treatment": "standard",
            "deemed_input_supply": 0, "deemed_input_eligible": None, "deemed_input_document_type": None,
        },
        "business": {
            "verification_status": "verified", "business_status": "active", "tax_type": "general",
            "tax_profile_confirmed": True, "entity_type": "individual",
            "industry_category": category, "industry_subtype": subtype,
        },
    }


def random_day(rng: random.Random) -> date:
    return date(2026, 1, 1) + timedelta(days=rng.randint(0, 300))


def synthetic_cases(groups: int, seed: int, prefix: str):
    rng = random.Random(seed)
    for issue in ISSUES:
        for g in range(groups):
            industry = rng.choice(issue.industries)
            vendor = rng.choice(issue.receipt.vendors)
            evidence = rng.choice(issue.receipt.evidence)
            picked = rng.sample(issue.receipt.items, rng.randint(1, min(3, len(issue.receipt.items))))
            items = [(name, rng.randint(1, 3), rng.randint(lo, hi) // 100 * 100) for name, lo, hi in picked]
            day = random_day(rng)
            group = f"{prefix}{issue.id}-{g}"
            # 같은 영수증의 사업자번호·시각이 변형마다 같도록 같은 시드로 만든다.
            receipt_seed = rng.random()
            for i, fact in enumerate(issue.facts):
                request = build_request(random.Random(receipt_seed), industry, vendor, items, evidence,
                                        fact.purpose, fact.business_related, day)
                expected = {"verdict": fact.verdict, "category": fact.category, "laws": list(fact.laws)}
                yield {"id": f"{group}-{i}", "group": group, "issue": issue.id, "fact": i, "expected": expected, "request": request}


def gold_cases(seed: int):
    rng = random.Random(seed)
    for gid, industry, vendor, items, evidence, purpose, related, verdict, category, laws, note in GOLD:
        request = build_request(rng, industry, vendor, [(name, 1, amount) for name, amount in items],
                                evidence, purpose, related, random_day(rng))
        expected = {"verdict": verdict, "category": category, "laws": list(laws), "note": note}
        yield {"id": gid, "group": gid, "issue": "gold", "expected": expected, "request": request}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--groups", type=int, default=6, help="쟁점마다 만들 영수증 수")
    parser.add_argument("--gold", action="store_true", help="합성 거래 대신 골드셋을 내보낸다")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--prefix", default="", help="id 앞에 붙일 문자(다른 실행분과 id가 겹치지 않게)")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    cases = list(gold_cases(args.seed) if args.gold else synthetic_cases(args.groups, args.seed, args.prefix))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(case, ensure_ascii=False) + "\n")

    counts = {}
    for case in cases:
        counts[case["expected"]["verdict"]] = counts.get(case["expected"]["verdict"], 0) + 1
    print(f"{len(cases)}건 → {args.out}  {counts}")


if __name__ == "__main__":
    main()
