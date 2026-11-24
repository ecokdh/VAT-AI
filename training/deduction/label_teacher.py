"""teacher 라벨링: 앱과 같은 그래프(규칙 → 법령 검색 → gpt 판정 → 검증)로 케이스를 판정하고 기준표 정답과 비교한다.

유료 OpenAI 호출(임베딩 + 판정)이라 --allow-paid 없이는 실행되지 않는다.
저장소 루트에서 실행한다(.env와 로컬 DB 필요, GPU 불필요).
    python training/deduction/label_teacher.py --allow-paid --cases training/deduction/data/cases.jsonl --out training/deduction/data/labeled.jsonl

이미 판정된 id는 건너뛰므로 중단해도 같은 명령으로 이어서 돌릴 수 있다. 오류로 끝난 건은 다시 시도한다.
"""

import argparse
import json
import sys
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.deduction.ai_client import MODEL_NAME, judge_with_laws  # noqa: E402
from app.deduction.analyzer import AnalysisRequest  # noqa: E402
from app.deduction.graph.adapter import _core_laws, _retrieve  # noqa: E402
from app.deduction.graph.graph import build_graph  # noqa: E402


def label(graph, case: dict) -> dict:
    request = AnalysisRequest(run_id=uuid.uuid4(), **case["request"])
    try:
        state = graph.invoke({"request": request})
    except Exception as exc:  # 한 건의 실패가 전체 실행을 멈추지 않게 기록만 한다.
        return {**case, "teacher": MODEL_NAME, "error": str(exc)}

    result = state["result"]
    judgement = state.get("judgement")
    return {
        **case,
        "teacher": MODEL_NAME,
        "laws": [law.model_dump() for law in state.get("laws", [])],
        "judgement": judgement.model_dump() if judgement else None,
        "verdict": result.verdict,
        "attempts": state.get("attempts", 0),
        "agree": result.verdict == case["expected"]["verdict"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--allow-paid", action="store_true", help="유료 OpenAI 호출을 허용한다(건당 약 $0.009)")
    args = parser.parse_args()
    if not args.allow_paid:
        sys.exit("유료 API 호출이라 막아 두었습니다. 비용을 쓰기로 했을 때만 --allow-paid를 붙이세요. 무료 라벨링은 label_template.py입니다.")

    done = []
    if args.out.exists():
        done = [row for row in map(json.loads, open(args.out, encoding="utf-8")) if "error" not in row]
        with open(args.out, "w", encoding="utf-8") as f:  # 오류 건은 지우고 다시 시도한다.
            f.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in done)
    done = {row["id"] for row in done}
    cases = [c for c in map(json.loads, open(args.cases, encoding="utf-8")) if c["id"] not in done]
    print(f"남은 {len(cases)}건 (완료 {len(done)}건), teacher={MODEL_NAME}")

    graph = build_graph(_retrieve, _core_laws, judge_with_laws)
    lock = Lock()
    with open(args.out, "a", encoding="utf-8") as f, ThreadPoolExecutor(args.workers) as pool:
        for i, row in enumerate(pool.map(lambda c: label(graph, c), cases), 1):
            with lock:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
            if i % 20 == 0:
                print(f"{i}/{len(cases)}")

    rows = [json.loads(line) for line in open(args.out, encoding="utf-8")]
    pairs = Counter((r["expected"]["verdict"], r.get("verdict", "error")) for r in rows)
    print(f"전체 {len(rows)}건, 일치 {sum(r.get('agree', False) for r in rows)}건")
    for (expected, got), n in sorted(pairs.items()):
        print(f"  기준표 {expected:15} → teacher {got:15} {n}")


if __name__ == "__main__":
    main()
