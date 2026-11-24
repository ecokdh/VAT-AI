"""공제 판정 sLLM을 골드셋(또는 검증 데이터)으로 평가한다. GPU 서버(DGX Spark)에서 실행한다.

기본 모델과 LoRA를 같은 데이터로 비교한다:
    python evaluate_slm.py --split gold --report outputs/eval_gold_base.json
    python evaluate_slm.py --split gold --adapter outputs/qwen3-4b-deduction/adapter --report outputs/eval_gold_lora.json

지표:
- 형식: JSON 해석률, 앱 verify 노드와 같은 검사 통과율
- 판정: 정확도, macro-F1, 혼동행렬, 오공제율(정답 불공제 → 공제로 판정)
- 신뢰도: verdict 첫 토큰 확률. 기준값별로 sLLM이 확정할 비율과 그 정확도·오공제율(라우팅 기준값 선택용)
- 속도: 건당 생성 시간
골드셋이면 teacher(gpt) 판정도 같은 정답으로 채점해 함께 보여 준다.
"""
import argparse
import json
import re
import time
from collections import Counter
from pathlib import Path

VERDICTS = ("deductible", "non_deductible", "ambiguous")
# app/deduction/graph/rules.py의 CATEGORIES와 같아야 한다.
CATEGORIES = ("원재료", "소모품비", "복리후생비", "차량유지비", "통신비", "임차료", "지급수수료",
              "광고선전비", "기업업무추진비", "유흥비", "개인지출", "기타")
THRESHOLDS = (0.5, 0.8, 0.9, 0.95, 0.99)
VERDICT_VALUE = re.compile(r'"verdict"\s*:\s*"')


def load_rows(data: Path, split: str, limit: int | None) -> list[dict]:
    rows = []
    for row in map(json.loads, open(data / f"{split if split != 'gold' else 'gold_eval'}.jsonl", encoding="utf-8")):
        expected = row["expected"]["verdict"] if split == "gold" else json.loads(row["answer"])["verdict"]
        teacher = (row.get("teacher") or {}).get("verdict") if split == "gold" else None
        rows.append({"id": row["id"], "system": row["system"], "prompt": row["prompt"],
                     "expected": expected, "teacher": teacher})
    return rows[:limit] if limit else rows


def parse(text: str) -> dict | None:
    """기본 모델은 ```json 울타리 등을 붙일 수 있어 첫 '{'부터 마지막 '}'까지만 읽는다."""
    start, end = text.find("{"), text.rfind("}")
    try:
        return json.loads(text[start:end + 1]) if start >= 0 else None
    except json.JSONDecodeError:
        return None


def ids(values) -> set[int]:
    """앱(pydantic)처럼 "597" 같은 숫자 문자열도 정수 id로 읽는다."""
    return {int(v) for v in values or [] if str(v).strip().isdigit()}


def verify(out: dict, law_ids: set[int]) -> list[str]:
    """app/deduction/graph/nodes.py의 validate와 같은 검사(앱 코드 없이 서버에서 돌리려고 옮겨 둠)."""
    errors = []
    if out.get("verdict") not in VERDICTS:
        return ["verdict 값 오류"]
    if out.get("category") not in CATEGORIES:
        errors.append("category 오류")
    if not str(out.get("reason") or "").strip():
        errors.append("reason 없음")
    cases = out.get("cases") or []
    cited = ids(out.get("cited_law_ids")) | {i for c in cases for i in ids(c.get("cited_law_ids"))}
    if cited - law_ids:
        errors.append("목록에 없는 조문 인용")
    if out["verdict"] != "ambiguous":
        if not out.get("cited_law_ids"):
            errors.append("근거 조문 없음")
        return errors
    if not str(out.get("decision_point") or "").strip():
        errors.append("decision_point 없음")
    if {c.get("result") for c in cases} != {"deductible", "non_deductible"}:
        errors.append("cases에 공제·불공제가 모두 있지 않음")
    if any(not str(c.get("reason") or "").strip() or not c.get("cited_law_ids") for c in cases):
        errors.append("case 사유·근거 없음")
    return errors


def verdict_confidence(tokenizer, token_ids: list[int], scores) -> float | None:
    """verdict 값이 시작되는 토큰의 생성 확률. 첫 토큰(ded/non/amb)에서 세 판정이 갈린다.
    기본 모델은 공백·```json을 붙이기도 하므로 '"verdict": "' 뒤 첫 글자가 나온 토큰을 찾는다."""
    import torch

    match = VERDICT_VALUE.search(tokenizer.decode(token_ids))
    if not match:
        return None
    for k in range(len(token_ids)):
        if len(tokenizer.decode(token_ids[: k + 1])) > match.end():
            return torch.softmax(scores[k][0].float(), dim=-1)[token_ids[k]].item()
    return None


def summarize(results: list[dict], judged_key: str = "pred") -> dict:
    n = len(results)
    pairs = Counter((r["expected"], r[judged_key]) for r in results)
    correct = sum(pairs[(v, v)] for v in VERDICTS)
    f1s = []
    for v in VERDICTS:
        tp = pairs[(v, v)]
        fp = sum(c for (e, p), c in pairs.items() if p == v and e != v)
        fn = sum(c for (e, p), c in pairs.items() if e == v and p != v)
        f1s.append(2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    non_deductible = sum(1 for r in results if r["expected"] == "non_deductible")
    return {
        "n": n,
        "accuracy": round(correct / n, 4) if n else None,
        "macro_f1": round(sum(f1s) / len(f1s), 4),
        "wrong_deduction_rate": round(pairs[("non_deductible", "deductible")] / non_deductible, 4) if non_deductible else None,
        "confusion": {f"{e}->{p}": c for (e, p), c in sorted(pairs.items(), key=str)},
    }


def routing(results: list[dict]) -> list[dict]:
    """기준값마다 sLLM이 확정하는 건(형식 통과·애매 아님·신뢰도 이상)의 비율과 품질."""
    table = []
    for t in THRESHOLDS:
        kept = [r for r in results if r["valid"] and r["pred"] != "ambiguous" and (r["confidence"] or 0) >= t]
        non_ded = [r for r in kept if r["expected"] == "non_deductible"]
        table.append({
            "threshold": t,
            "handled_by_slm": round(len(kept) / len(results), 4) if results else None,
            "accuracy": round(sum(r["pred"] == r["expected"] for r in kept) / len(kept), 4) if kept else None,
            "wrong_deduction": sum(r["pred"] == "deductible" for r in non_ded),
        })
    return table


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--split", choices=("gold", "val"), default="gold")
    parser.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507")
    parser.add_argument("--adapter", type=Path, help="없으면 기본 모델(파인튜닝 전)을 평가한다")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.adapter or args.model)
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.bfloat16, attn_implementation="sdpa", device_map="cuda")
    if args.adapter:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, args.adapter)
    model.eval()

    results = []
    rows = load_rows(args.data, args.split, args.limit)
    for i, row in enumerate(rows, 1):
        messages = [{"role": "system", "content": row["system"]}, {"role": "user", "content": row["prompt"]}]
        inputs = tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt", return_dict=True).to(model.device)
        started = time.perf_counter()
        with torch.no_grad():
            generated = model.generate(**inputs, max_new_tokens=args.max_new_tokens, do_sample=False,
                                       return_dict_in_generate=True, output_scores=True)
        seconds = time.perf_counter() - started
        token_ids = generated.sequences[0][inputs["input_ids"].shape[1]:].tolist()
        text = tokenizer.decode(token_ids, skip_special_tokens=True)
        out = parse(text)
        law_ids = set(map(int, re.findall(r"\[id=(\d+)\]", row["prompt"])))
        errors = verify(out, law_ids) if out else ["JSON 해석 실패"]
        results.append({
            "id": row["id"], "expected": row["expected"], "teacher": row["teacher"],
            "pred": out.get("verdict") if out else None, "valid": not errors, "errors": errors,
            "confidence": verdict_confidence(tokenizer, token_ids, generated.scores),
            "seconds": round(seconds, 2), "output": text,
        })
        confidence = results[-1]["confidence"]
        print(f"{i}/{len(rows)} {row['id']}: {row['expected']} → {results[-1]['pred']} "
              f"(conf {'-' if confidence is None else f'{confidence:.3f}'}, {seconds:.1f}s"
              f"{', ' + '; '.join(errors) if errors else ''})")

    times = sorted(r["seconds"] for r in results)
    summary = {
        "model": args.model, "adapter": str(args.adapter) if args.adapter else None, "split": args.split,
        "json_ok": round(sum(r["pred"] is not None for r in results) / len(results), 4),
        "verify_ok": round(sum(r["valid"] for r in results) / len(results), 4),
        **summarize(results),
        "routing": routing(results),
        "seconds_mean": round(sum(times) / len(times), 2),
        "seconds_p90": times[int(len(times) * 0.9) - 1] if len(times) >= 10 else times[-1],
    }
    if args.split == "gold":
        teacher = [r for r in results if r["teacher"]]
        summary["teacher"] = summarize(teacher, "teacher") if teacher else None

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
