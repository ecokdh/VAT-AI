"""teacher 라벨을 SFT 데이터(system·prompt·answer)로 바꾼다. 저장소 루트에서 실행, GPU·DB 불필요.

    python training/deduction/make_dataset.py --data training/deduction/data --labeled labeled.jsonl labeled_template.jsonl

- 학습: 라벨 파일들 중 기준표 정답과 판정이 일치한 것만 쓴다 → train.jsonl / val.jsonl (영수증 group 단위로 나눔)
  템플릿 라벨은 기준표에서 만들었으므로 항상 일치한다.
- 평가: gold_teacher.jsonl → gold_eval.jsonl. 정답은 teacher가 아니라 골드셋 정답이며, 학습에는 넣지 않는다.
- 조문 id는 매번 무작위 번호로 바꾸고 순서도 섞는다. 모델이 DB 번호를 외우지 않고 목록에서 찾아 인용하게 하려는 것이다.
"""

import argparse
import json
import random
import sys
import uuid
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.deduction.analyzer import AnalysisRequest  # noqa: E402
from app.deduction.graph.prompts import INSTRUCTIONS, build_input  # noqa: E402
from app.deduction.graph.state import JudgeOutput  # noqa: E402
from app.deduction.rag.schemas import LawOut  # noqa: E402


def remap_laws(rng: random.Random, laws: list[dict]) -> tuple[list[LawOut], dict[int, int]]:
    new_ids = rng.sample(range(1, 1000), len(laws))
    mapping = {law["id"]: new for law, new in zip(laws, new_ids)}
    remapped = [LawOut(**{**law, "id": mapping[law["id"]]}) for law in laws]
    rng.shuffle(remapped)
    return remapped, mapping


def remap_judgement(judgement: dict, mapping: dict[int, int]) -> JudgeOutput:
    cases = [{**case, "cited_law_ids": [mapping[i] for i in case["cited_law_ids"]]} for case in judgement["cases"]]
    return JudgeOutput(**{**judgement, "cited_law_ids": [mapping[i] for i in judgement["cited_law_ids"]], "cases": cases})


def prompt_of(row: dict, laws: list[LawOut]) -> str:
    return build_input(AnalysisRequest(run_id=uuid.uuid4(), **row["request"]), laws, [])


def sft_row(rng: random.Random, row: dict) -> dict:
    laws, mapping = remap_laws(rng, row["laws"])
    answer = remap_judgement(row["judgement"], mapping).model_dump_json()
    return {"id": row["id"], "group": row["group"], "system": INSTRUCTIONS, "prompt": prompt_of(row, laws), "answer": answer}


def eval_row(rng: random.Random, row: dict) -> dict:
    laws, mapping = remap_laws(rng, row["laws"])
    teacher = remap_judgement(row["judgement"], mapping).model_dump() if row.get("judgement") else None
    return {"id": row["id"], "system": INSTRUCTIONS, "prompt": prompt_of(row, laws),
            "expected": row["expected"], "teacher": teacher, "law_ids": sorted(mapping.values())}


def usable(row: dict) -> bool:
    return bool(row.get("laws")) and row.get("judgement") is not None and row.get("verdict") != "failed"


def write(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--labeled", nargs="+", default=["labeled.jsonl"], help="--data 안의 라벨 파일들")
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    rng = random.Random(args.seed)

    labeled = [json.loads(line) for name in args.labeled for line in open(args.data / name, encoding="utf-8")]
    kept = [row for row in labeled if row.get("agree") and usable(row)]
    groups = sorted({row["group"] for row in kept})
    val_groups = set(rng.sample(groups, max(1, round(len(groups) * args.val_ratio))))
    train = [sft_row(rng, row) for row in kept if row["group"] not in val_groups]
    val = [sft_row(rng, row) for row in kept if row["group"] in val_groups]
    write(args.data / "train.jsonl", train)
    write(args.data / "val.jsonl", val)

    gold = [eval_row(rng, row) for row in map(json.loads, open(args.data / "gold_teacher.jsonl", encoding="utf-8"))
            if row.get("laws")]
    write(args.data / "gold_eval.jsonl", gold)

    meta = {"labeled": len(labeled), "kept": len(kept), "train": len(train), "val": len(val), "gold": len(gold),
            "teachers": dict(Counter(row["teacher"] for row in kept))}
    (args.data / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(meta)


if __name__ == "__main__":
    main()
