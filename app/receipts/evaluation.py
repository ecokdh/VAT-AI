"""Offline same-cache evaluation; no provider requests or database writes."""
import argparse
from collections import Counter
from dataclasses import asdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from app.receipts.ocr_client import parse_response, collect_partial
from app.receipts.money import complete_money

FIELDS = {"vendor": "vendor", "business_number": "business_number", "date": "date",
          "taxable_supply_amount": "taxable_supply_amount", "tax_exempt_amount": "tax_exempt_amount",
          "vat_amount": "vat_amount", "transaction_amount": "receipt_total_amount",
          "payment_amount": "payment_amount", "subtotal_amount": "subtotal_amount"}
ITEM_FIELDS = {"quantity": "quantity", "printed_unit_price": "unit_price_printed", "line_amount": "line_amount"}


def printed_targets(truth):
    targets = {field: truth["printed"].get(target) for field, target in FIELDS.items()}
    if "주문" in truth["printed"].get("document_type", ""):
        # An order's printed pre-discount total is not a transaction total.
        targets["transaction_amount"] = None
        targets["subtotal_amount"] = truth["printed"].get("subtotal_amount") or truth["printed"].get("receipt_total_amount")
    return targets


def normalize(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return str(Decimal(str(value)).normalize())
    return re.sub(r"\s", "", unicodedata.normalize("NFKC", str(value)))


def score(expected, predicted):
    expected, predicted = normalize(expected), normalize(predicted)
    return {"tp": int(expected is not None and expected == predicted),
            "fp": int(predicted is not None and predicted != expected),
            "fn": int(expected is not None and predicted != expected),
            "present": int(expected is not None), "exact_present": int(expected is not None and expected == predicted),
            "absent": int(expected is None), "false_present": int(expected is None and predicted is not None)}


def metrics(counts):
    tp, fp, fn = (counts[k] for k in ("tp", "fp", "fn"))
    return {**counts, "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
            "exact_match_rate": counts["exact_present"] / counts["present"] if counts["present"] else None}


def evaluate_record(truth, prediction):
    scores, errors = {}, []
    targets = printed_targets(truth)
    for field, target in FIELDS.items():
        expected, actual = targets[field], prediction.get(field)
        scores[field] = score(expected, actual)
        if normalize(expected) != normalize(actual):
            errors.append({"field": field, "expected": expected, "predicted": actual})
    gold = truth["line_items"]
    predicted = prediction.get("line_items") or [{"name": name} for name in prediction.get("items", [])]
    unmatched = list(range(len(gold)))
    item_scores = {field: Counter() for field in ("name", *ITEM_FIELDS)}
    matches, item_errors = [], []
    exact_rows = 0
    for predicted_index, item in enumerate(predicted):
        match = next((i for i in unmatched if normalize(gold[i]["name"]) == normalize(item["name"])), None)
        if match is not None:
            unmatched.remove(match)
            matches.append({"expected_row": match, "predicted_row": predicted_index, "name": item["name"]})
            exact_rows += int(all(normalize(gold[match].get(target)) == normalize(item.get(field)) for field, target in ITEM_FIELDS.items()))
        for field, target in {"name": "name", **ITEM_FIELDS}.items():
            expected, actual = gold[match].get(target) if match is not None else None, item.get(field)
            item_scores[field].update(score(expected, actual))
            if normalize(expected) != normalize(actual):
                item_errors.append({"expected_row": match, "predicted_row": predicted_index, "field": field,
                    "expected": expected, "predicted": actual, "reason": "unmatched_item_name" if match is None else "value_mismatch"})
    for match in unmatched:
        for field, target in {"name": "name", **ITEM_FIELDS}.items():
            item_scores[field].update(score(gold[match].get(target), None))
            if gold[match].get(target) is not None:
                item_errors.append({"expected_row": match, "predicted_row": None, "field": field,
                    "expected": gold[match][target], "predicted": None, "reason": "missing_item"})
    numeric_errors = sum(c["fp"] + c["fn"] for c in item_scores.values())
    return scores, item_scores, {"id": truth["id"], "field_errors": errors,
            "unmatched_expected_rows": unmatched, "item_matches": matches,
            "item_field_errors": item_errors,
            "row_link_counts": {"expected_rows": len(gold), "predicted_rows": len(predicted), "matched_names": len(matches), "exact_rows": exact_rows},
            "item_error_count": numeric_errors, "correction_needed": bool(errors or numeric_errors),
            "review_reasons": prediction.get("review_reasons", [])}


def run(root: Path):
    truth = [json.loads(line) for line in (root / "test_dataset.jsonl").read_text(encoding="utf-8").splitlines()]
    before = {row["id"]: row for row in json.loads((root / "before_document_ai.json").read_text(encoding="utf-8"))["records"]}
    totals = {mode: {"fields": {f: Counter() for f in FIELDS}, "items": {f: Counter() for f in ("name", *ITEM_FIELDS)}, "records": []} for mode in ("existing", "improved")}
    predictions, exclusions = [], []
    calculation_counts = {f: Counter() for f in ("taxable_supply_amount", "tax_exempt_amount", "vat_amount")}
    calculation_records = []
    for row in truth:
        cache = root / before[row["id"]]["cache"]
        digest = hashlib.sha256(cache.read_bytes()).hexdigest()
        if digest != before[row["id"]]["cache_sha256"]:
            raise ValueError(f"Cached response changed: {row['id']}")
        envelope = json.loads(cache.read_text(encoding="utf-8"))
        payload = envelope["payload"]
        parsed = parse_response(payload) or collect_partial(payload)
        improved = json.loads(json.dumps(asdict(parsed) if parsed else {}, default=str))
        pair = {"existing": before[row["id"]]["prediction"], "improved": improved}
        predictions.append({"id": row["id"], "cache_sha256": digest, **pair})
        targets = printed_targets(row)
        money = {f: targets[f] for f in ("taxable_supply_amount", "tax_exempt_amount", "vat_amount", "transaction_amount", "payment_amount", "subtotal_amount")}
        computed, sources = complete_money(money, {f: {"kind": "printed"} for f, value in money.items() if value is not None})
        calculation_errors = []
        for f in calculation_counts:
            if money[f] is None and row.get("derived", {}).get(f) is not None:
                expected = row["derived"][f]
                actual = computed.get(f)
                calculation_counts[f].update(score(expected, actual))
                if normalize(expected) != normalize(actual):
                    calculation_errors.append({"field": f, "expected": expected, "predicted": actual})
        calculation_records.append({"id": row["id"], "errors": calculation_errors, "sources": sources})
        for mode, prediction in pair.items():
            fields, items, record = evaluate_record(row, prediction)
            for f, counts in fields.items():
                totals[mode]["fields"][f].update(counts)
            for f, counts in items.items():
                totals[mode]["items"][f].update(counts)
            totals[mode]["records"].append(record)
    result = {"dataset_size": len(truth), "exclusions": exclusions, "excluded_count": len(exclusions),
              "truth_status": "User approximately accepted original readings; expanded values are assistant transcriptions without independent validation.",
              "scope": "Same stored CLOVA responses; printed targets only. No new OCR calls or preprocessing/OCR comparison.",
              "predictions": predictions}
    result["calculation_rules"] = {"scope": "Rules supplied with reference printed amounts; this is not OCR performance.",
        "fields": {f: metrics(c) for f, c in calculation_counts.items()}, "records": calculation_records}
    for mode, data in totals.items():
        row_counts = Counter()
        for record in data["records"]:
            row_counts.update(record["row_link_counts"])
        correct, expected, predicted = (row_counts[key] for key in ("exact_rows", "expected_rows", "predicted_rows"))
        result[mode] = {"fields": {f: metrics(c) for f, c in data["fields"].items()},
                        "items": {f: metrics(c) for f, c in data["items"].items()},
                        "item_row_linking": {**row_counts, "precision": correct / predicted if predicted else None,
                            "recall": correct / expected if expected else None, "f1": 2 * correct / (predicted + expected) if predicted + expected else None,
                            "scope": "Exact name and every printed quantity/price/line amount on the same one-to-one row; absent values must stay absent."},
                        "correction_needed_rate": sum(r["correction_needed"] for r in data["records"]) / len(truth),
                        "records": data["records"]}
    (root / "document_ai_comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "document_ai_failures.jsonl").write_text("\n".join(json.dumps({"mode": mode, **record}, ensure_ascii=False) for mode, data in totals.items() for record in data["records"] if record["correction_needed"]) + "\n", encoding="utf-8")
    report = ["# 저장 응답 30건 Document AI 비교", "", result["truth_status"], "", result["scope"], "",
              "품목 이름은 공백 제거·Unicode 정규화 후 정확 일치로 연결한다. 반복 품목은 일대일로 소비하며 숫자는 연결된 행에서만 평가한다.",
              "미기재 기대값에 추출값이 있으면 FP이다. 인쇄값과 계산값은 혼합하지 않는다. 평가 데이터 30건 제외 0건.", "",
              "| 필드 | 기존 F1 | 개선 F1 | 기존 정확 일치율 | 개선 정확 일치율 |", "|---|---:|---:|---:|---:|"]
    def fmt(value):
        return "N/A" if value is None else f"{value:.3f}"
    for section in ("fields", "items"):
        for f in result["existing"][section]:
            a, b = result["existing"][section][f], result["improved"][section][f]
            report.append(f"| {section}.{f} | {fmt(a['f1'])} | {fmt(b['f1'])} | {fmt(a['exact_match_rate'])} | {fmt(b['exact_match_rate'])} |")
    report.extend(["", f"수정 필요 비율: 기존 {fmt(result['existing']['correction_needed_rate'])}, 개선 {fmt(result['improved']['correction_needed_rate'])}.",
                   "", "행 전체 연결은 품목명이 일치하고 수량·인쇄 단가·행 금액이 모두 같은 행에 정확히 연결된 경우만 성공으로 센다. 실제 미기재 숫자에 임의 값을 넣어도 실패다.",
                   "", "| 추출 방식 | 정답 행 | 추출 행 | 이름 연결 행 | 전체 정확 행 | 행 연결 Precision | Recall | F1 |",
                   "|---|---:|---:|---:|---:|---:|---:|---:|"])
    for mode in ("existing", "improved"):
        row = result[mode]["item_row_linking"]
        report.append(f"| {mode} | {row['expected_rows']} | {row['predicted_rows']} | {row['matched_names']} | {row['exact_rows']} | {fmt(row['precision'])} | {fmt(row['recall'])} | {fmt(row['f1'])} |")
    report.extend([
                   "", "실패 JSONL에는 정답·추출 행 번호와 필드별 기대값·추출값·실패 사유를 함께 기록한다.",
                   "", "계산 규칙은 정답의 인쇄 금액을 입력한 별도 평가이며 OCR 점수에 합산하지 않는다. 상세 결과는 JSON의 calculation_rules에 기록했다.",
                   "", "추가 품목·금액 정답은 독립 검증되지 않았으므로 이 결과는 잠정 Baseline이다. 품질 모델 실험과 실제 촬영환경 성능은 이 보고서에 포함되지 않는다."])
    (root / "document_ai_comparison.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps({mode: {"correction_needed_rate": result[mode]["correction_needed_rate"], "item_name_f1": result[mode]["items"]["name"]["f1"]} for mode in totals}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    run(parser.parse_args().root)
