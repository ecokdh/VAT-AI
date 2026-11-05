"""가상 값을 채운 신고서 이미지와 정답(JSON)을 만든다.

과제는 두 가지다.
- read: 채워진 신고서 이미지 → 칸별 값 JSON (덧입힌 결과 검증용)
- locate: 칸 이름 → 그 칸의 bbox_2d (양식 개정 시 칸 좌표 자동 추출용)

예) python training/make_dataset.py --count 1500 --out training/data
"""
import argparse
import json
import random
from pathlib import Path

import pypdfium2 as pdfium

from vatform.fields import FIELD_BY_ID, FIELDS, PAGE_HEIGHT, PAGE_WIDTH, normalized_box
from vatform.fill import fill_page1
from vatform.prompts import LOCATE_PROMPT, READ_PROMPT
from vatform.sample import sample_return


def render(pdf: bytes, width: int):
    # Qwen3-VL은 32px 단위로 이미지를 자르므로 가로·세로를 32의 배수로 맞춘다.
    height = round(width * PAGE_HEIGHT / PAGE_WIDTH / 32) * 32
    page = pdfium.PdfDocument(pdf)[0]
    return page.render(scale=width / PAGE_WIDTH).to_pil().convert("L").resize((width, height))


def records_for(image: str, values: dict[str, str], rng: random.Random, locate_per_image: int) -> list[dict]:
    records = []
    if values:
        ordered = {f.id: values[f.id] for f in FIELDS if f.id in values}
        records.append({"image": image, "task": "read", "prompt": READ_PROMPT,
                        "answer": json.dumps(ordered, ensure_ascii=False)})
    for field in rng.sample(FIELDS, locate_per_image):
        answer = {"bbox_2d": normalized_box(field), "label": field.id}
        records.append({"image": image, "task": "locate", "prompt": LOCATE_PROMPT.format(label=field.label),
                        "answer": json.dumps(answer, ensure_ascii=False)})
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "data")
    parser.add_argument("--count", type=int, default=1500, help="만들 이미지 수")
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--width", type=int, default=1280, help="이미지 가로(px), 32의 배수")
    parser.add_argument("--blank-ratio", type=float, default=0.05, help="빈 양식 비율(locate만 만든다)")
    parser.add_argument("--locate-per-image", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    (args.out / "images").mkdir(parents=True, exist_ok=True)
    splits = {"train": [], "val": []}
    for i in range(args.count):
        values = {} if rng.random() < args.blank_ratio else sample_return(rng)
        image = f"images/{i:05d}.png"
        render(fill_page1(values), args.width).save(args.out / image, optimize=True)
        split = "val" if rng.random() < args.val_ratio else "train"
        splits[split] += records_for(image, values, rng, args.locate_per_image)
        if (i + 1) % 100 == 0:
            print(f"{i + 1}/{args.count}")

    for split, rows in splits.items():
        with open(args.out / f"{split}.jsonl", "w", encoding="utf-8") as f:
            f.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    meta = {"form": "별지 제21호서식(2026. 3. 20. 개정) 1쪽", "width": args.width, "seed": args.seed,
            "fields": {f.id: {"label": f.label, "bbox_2d": normalized_box(f)} for f in FIELD_BY_ID.values()}}
    (args.out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print({split: len(rows) for split, rows in splits.items()})


if __name__ == "__main__":
    main()
