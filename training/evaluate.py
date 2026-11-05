"""검증 데이터로 성능을 잰다. --adapter를 빼면 파인튜닝 전 기본 모델(제로샷) 성능이 나온다.

    python evaluate.py --data data --adapter outputs/qwen3vl4b-lora/adapter --limit 200
    python evaluate.py --data data --limit 200            # 비교용 기본 모델
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

from vatform.prompts import user_message


def parse_json(text: str):
    start, end = text.find("{"), text.rfind("}")
    try:
        return json.loads(text[start:end + 1])
    except (ValueError, TypeError):
        return None


def iou(a, b) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def score(task: str, answer: dict, predicted) -> dict:
    if predicted is None:
        return {"parsed": 0}
    if task == "read":
        keys = set(answer) | set(predicted)
        correct = sum(answer.get(k) == predicted.get(k) for k in keys)
        return {"parsed": 1, "field_acc": correct / len(keys), "doc_exact": int(answer == predicted)}
    box = predicted.get("bbox_2d")
    overlap = iou(answer["bbox_2d"], box) if isinstance(box, list) and len(box) == 4 else 0.0
    return {"parsed": 1, "iou": overlap, "hit@0.5": int(overlap >= 0.5)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--model", default="Qwen/Qwen3-VL-4B-Instruct")
    parser.add_argument("--adapter", type=Path)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--report", type=Path, default=Path("outputs/eval.json"))
    args = parser.parse_args()

    processor = AutoProcessor.from_pretrained(args.model)
    model = Qwen3VLForConditionalGeneration.from_pretrained(args.model, dtype=torch.bfloat16, device_map="auto")
    if args.adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, args.adapter)
    model.eval()

    rows = [json.loads(line) for line in open(args.data / "val.jsonl", encoding="utf-8")][: args.limit]
    totals, samples = defaultdict(lambda: defaultdict(float)), []
    for n, row in enumerate(rows, 1):
        text = processor.apply_chat_template([user_message(row["prompt"])], tokenize=False, add_generation_prompt=True)
        image = Image.open(args.data / row["image"]).convert("RGB")
        inputs = processor(text=[text], images=[image], return_tensors="pt").to(model.device)
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=1024 if row["task"] == "read" else 64, do_sample=False)
        output = processor.batch_decode(out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)[0]
        result = score(row["task"], json.loads(row["answer"]), parse_json(output))
        totals[row["task"]]["count"] += 1
        for key, value in result.items():
            totals[row["task"]][key] += value
        if len(samples) < 20:
            samples.append({"image": row["image"], "task": row["task"], "output": output, **result})
        if n % 20 == 0:
            print(f"{n}/{len(rows)}")

    summary = {task: {k: (v if k == "count" else round(v / t["count"], 4)) for k, v in t.items()} for task, t in totals.items()}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({"adapter": str(args.adapter), "summary": summary, "samples": samples},
                                      ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
