# 공제 판정 sLLM 학습 데이터 (Qwen3-4B LoRA용)

앱의 공제 그래프와 같은 입력(거래 + 조문 12개)과 출력(`JudgeOutput` JSON)으로 소형 모델을 학습시킨다.
이 폴더의 단계는 모두 이 PC에서 돈다(GPU 불필요). 학습·평가만 DGX에서 한다.

| 파일 | 역할 |
|---|---|
| `criteria.py` | 판정 기준표 — 쟁점별 영수증 틀, '확인된 사실 → 정답·근거 조문·사유 문장 틀' |
| `gold.py` | 평가 전용 골드셋(기준표와 상호·품목이 겹치지 않음, 학습에 섞지 않음). 사용자 검수 전 초안 |
| `make_cases.py` | 기준표·골드셋 → 앱 `AnalysisRequest` 형식 케이스 |
| `label_template.py` | **무료 라벨링(기본)** — 기준표로 정답·사유를 만든다. API·DB 호출 없음 |
| `label_teacher.py` | 유료 라벨링(앱 그래프 + gpt). `--allow-paid` 없이는 실행되지 않는다 |
| `make_dataset.py` | 라벨들 → SFT 데이터. 조문 id 무작위 재번호·순서 섞기 |

`label_template.py`는 프롬프트에 넣을 조문 목록을 `labeled.jsonl`(시범 teacher 라벨 288건)에서 같은 쟁점 것을 빌려 쓴다.

## 실행 (`.venv`)

```bash
cd training/deduction
python make_cases.py --groups 100 --seed 11 --prefix t- --out data/cases_t.jsonl
python make_cases.py --gold --out data/gold.jsonl
python label_template.py --cases data/cases_t.jsonl --laws-from data/labeled.jsonl --out data/labeled_template.jsonl
cd ../..
python training/deduction/make_dataset.py --data training/deduction/data --labeled labeled.jsonl labeled_template.jsonl
```

결과: `data/train.jsonl`, `val.jsonl`(한 줄 = `system`·`prompt`·`answer`), `gold_eval.jsonl`(골드 정답 + teacher 판정), `meta.json`.
서버에는 이 jsonl만 올린다. 가상 거래와 공개 법령 조문뿐이며 실데이터·`.env`는 없다.

## 학습 (DGX Spark)

VS Code Remote-SSH 탐색기로 아래 파일만 `~/vat-ai-dong/training/deduction/`에 올린다.

```
train_slm.py
data/train.jsonl  data/val.jsonl  data/gold_eval.jsonl
```

신고서 모델과 같은 가상환경을 쓴다(torch는 이미 설치됨). 모델 파일(약 8GB)은 내 폴더 캐시에 받는다.

```bash
source ~/vat-ai-dong/.venv/bin/activate
export HF_HOME=~/vat-ai-dong/hf-cache
cd ~/vat-ai-dong/training/deduction
```

설정 확인용 짧은 실행(8개, 2단계). `[data]` 줄의 최대 토큰 길이와 `[mask]` 줄의 학습 대상이 답변 JSON뿐인지 확인한다.

```bash
python train_slm.py --data data --output outputs/smoke --smoke
```

본 학습은 `tmux` 안에서 돌린다. 1 에폭 약 220단계(3,544건 ÷ 16). 끊기면 같은 명령에 `--resume`을 붙인다.

```bash
python train_slm.py --data data --output outputs/qwen3-4b-deduction
```

결과: `outputs/qwen3-4b-deduction/adapter`(LoRA 가중치). 이 PC로 내려받아 보관한다.

## 평가 (DGX Spark)

`evaluate_slm.py`도 같은 폴더에 올린다. 골드셋 50건으로 기본 모델과 LoRA를 비교한다(학습 전에도 기본 모델은 돌릴 수 있다).

```bash
python evaluate_slm.py --split gold --report outputs/eval_gold_base.json
```

```bash
python evaluate_slm.py --split gold --adapter outputs/qwen3-4b-deduction/adapter --report outputs/eval_gold_lora.json
```

검증 데이터로도 볼 수 있다: `--split val --limit 200`.

| 지표 | 뜻 |
|---|---|
| `json_ok` / `verify_ok` | JSON 해석률 / 앱 verify 노드와 같은 검사 통과율 |
| `accuracy`, `macro_f1`, `confusion` | 판정 정확도 |
| `wrong_deduction_rate` | 오공제율 — 정답 불공제를 공제로 판정한 비율(가장 위험한 오류) |
| `routing` | 신뢰도 기준값별로 sLLM이 확정하는 비율과 그 정확도·오공제 건수(라우팅 기준값 선택용) |
| `seconds_mean`, `seconds_p90` | 건당 생성 시간 |
| `teacher` | 골드셋일 때 gpt(teacher) 판정을 같은 정답으로 채점한 결과 |

`verify`는 앱의 `validate`를, `CATEGORIES`는 `app/deduction/graph/rules.py`를 옮겨 둔 것이다. 앱 쪽을 고치면 함께 맞춘다.

## 판정 서버 (DGX Spark)

`serve_slm.py`도 같은 폴더에 올린다(`evaluate_slm.py`의 함수를 쓴다). 학습과 겹치지 않게 tmux 세션을 따로 연다.

```bash
tmux new -s serve
```

```bash
source ~/vat-ai-dong/.venv/bin/activate && cd ~/vat-ai-dong/training/deduction && export HF_HOME=~/vat-ai-dong/hf-cache && uvicorn serve_slm:app --host 127.0.0.1 --port 8002
```

`Application startup complete`가 나오면 `Ctrl+B` → `D`로 빠져나온다. VS Code '포트' 탭에 8002가 전달되면 이 PC의 `localhost:8002`로 닿는다
(자동으로 안 뜨면 포트 탭에서 8002를 직접 추가한다).

이 PC에서 골드셋 사례로 호출해 본다(표준 라이브러리만 사용).

```bash
python training/deduction/try_slm.py g20 g11 g33
```

- 공유 서버라 `127.0.0.1`로만 연다. 실제 사용자 거래 정보가 서버로 가므로 시연은 가상 거래로 한다.
- 신고서 검증 서버(8001)와 포트가 다르므로 둘을 함께 띄울 수 있다.
