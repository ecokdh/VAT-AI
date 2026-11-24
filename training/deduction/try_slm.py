"""이 PC에서 판정 서버(serve_slm.py)를 골드셋 사례로 호출해 본다. 표준 라이브러리만 쓴다.

    python try_slm.py                 # g20(접대 식사)
    python try_slm.py g11 g33 g24     # 여러 건
    python try_slm.py --url http://localhost:8002 g01
"""
import argparse
import json
import re
import urllib.request
from pathlib import Path

DATA = Path(__file__).parent / "data" / "gold_eval.jsonl"


def call(url: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ids", nargs="*", default=["g20"])
    parser.add_argument("--url", default="http://localhost:8002")
    args = parser.parse_args()

    print("health:", call(args.url, "/health"))
    rows = {row["id"]: row for row in map(json.loads, open(DATA, encoding="utf-8"))}
    for gid in args.ids:
        row = rows[gid]
        laws = dict(re.findall(r"\[id=(\d+)\] ([^\n]+)", row["prompt"]))
        result = call(args.url, "/judge", {"system": row["system"], "prompt": row["prompt"]})
        out = result["output"] or {}
        print(f"\n== {gid} ({row['expected'].get('note') or row['expected']['verdict']})")
        print(f"정답 {row['expected']['verdict']} → 모델 {out.get('verdict')}  (신뢰도 {result['confidence']}, {result['seconds']}초)")
        print("분류:", out.get("category"))
        print("사유:", out.get("reason"))
        print("근거:", [laws.get(str(i), f"목록에 없음({i})") for i in out.get("cited_law_ids", [])])
        if out.get("decision_point"):
            print("확인할 사실:", out["decision_point"])
            for case in out.get("cases", []):
                print(f"  - {case['condition']}: {case['result']} — {case['reason']}")


if __name__ == "__main__":
    main()
