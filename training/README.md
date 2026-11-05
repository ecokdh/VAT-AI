# 신고서 칸 인식 모델 (Qwen3-VL-4B LoRA)

부가가치세 신고서(별지 제21호서식, 2026. 3. 20. 개정) 1쪽을 대상으로 두 가지 과제를 학습한다.

| 과제 | 입력 | 출력 | 쓰임 |
|---|---|---|---|
| `read` | 값이 채워진 신고서 이미지 | `{"필드ID": "값"}` JSON | 앱이 덧입힌 PDF가 맞게 찍혔는지 다시 읽어 검증 |
| `locate` | 신고서 이미지 + 칸 이름 | `{"bbox_2d": [x1,y1,x2,y2], "label": "필드ID"}` (0~1000 상대 좌표) | 양식이 개정됐을 때 칸 좌표 자동 추출 |

신고서 금액은 모델이 만들지 않는다. 금액은 세액 계산 코드가 정하고, `vatform/fill.py`가 좌표에 그대로 찍는다.

## 구성

```
training/
├── assets/vat_return_form21_2026.pdf   # 빈 양식 원본
├── vatform/
│   ├── fields.py    # 칸 좌표(PDF 포인트)와 필드 ID·이름
│   ├── fill.py      # 빈 양식에 값 덧입히기 (reportlab + pypdf)
│   ├── sample.py    # 양식 계산식을 따르는 가상 신고 값
│   └── prompts.py   # 학습·평가 공통 지시문
├── make_dataset.py  # 합성 데이터 생성 (GPU 불필요)
├── train_lora.py    # LoRA 파인튜닝 (GPU 서버)
├── evaluate.py      # 검증 데이터 평가 (GPU 서버)
└── scripts/inspect_form.py  # 양식 개정 시 좌표 다시 뽑는 도구
```

## 1. 데이터 만들기 (이 PC)

```bash
python -m venv training/.venv-data
training/.venv-data/Scripts/python -m pip install -r training/requirements-data.txt
cd training && .venv-data/Scripts/python make_dataset.py --count 1500 --out data
```

- 이미지 1,500장(1280×1824, 흑백 PNG)과 `train.jsonl`, `val.jsonl`, `meta.json`이 `training/data/`에 생긴다.
- 한글 폰트가 필요하다. Windows는 맑은 고딕을 자동으로 쓰고, 다른 환경은 `VAT_FORM_FONT`에 TTF 경로를 준다.
- 상호·성명·주소·사업자번호는 모두 무작위로 만든 가상 값이다.

## 2. 서버로 올리기

VS Code Remote-SSH 창의 탐색기에 `training` 폴더를 끌어다 놓아 `~/vat-ai-dong/training`으로 올린다.
`.env` 같은 비밀 정보는 올리지 않는다(공유 계정).

## 3. 서버 환경 (DGX Spark, ARM64)

NGC PyTorch 컨테이너를 쓰면 ARM64·Blackwell용 torch/torchvision이 이미 들어 있다.
태그는 서버에서 `docker images`나 NGC 카탈로그로 최신 것을 고른다.

```bash
docker run --gpus all -it --rm --ipc=host -v ~/vat-ai-dong:/workspace -w /workspace/training nvcr.io/nvidia/pytorch:<태그>
```

```bash
pip install -r requirements-train.txt
```

모델 파일(약 9GB)은 내 폴더 안에 받도록 캐시 위치를 지정한다.

```bash
export HF_HOME=/workspace/hf-cache
```

## 4. 학습

설정 확인용 짧은 실행(8개, 2단계):

```bash
python train_lora.py --data data --output outputs/smoke --smoke
```

본 학습은 `tmux` 안에서 돌린다(창을 닫아도 계속 돈다).

```bash
python train_lora.py --data data --output outputs/qwen3vl4b-lora
```

## 5. 평가

기본 모델(파인튜닝 전)과 비교한다.

```bash
python evaluate.py --data data --limit 200 --report outputs/eval_base.json
```

```bash
python evaluate.py --data data --adapter outputs/qwen3vl4b-lora/adapter --limit 200 --report outputs/eval_lora.json
```

지표:
- `read`: `field_acc`(칸별 일치율), `doc_exact`(문서 전체 일치)
- `locate`: `iou`(평균 겹침), `hit@0.5`(IoU 0.5 이상 비율)

학습이 끝나면 `outputs/qwen3vl4b-lora/adapter`(LoRA 가중치, 수십 MB)를 이 PC로 내려받아 보관한다. 서버는 2달 뒤 닫힌다.

## 6. 앱과 연결 (검증 서버)

앱은 신고서 PDF를 만든 뒤 1쪽 이미지를 이 서버로 보내 다시 읽고, 넣으려던 값과 칸별로 대조한다(`app/vat_form/verifier.py`).
서버가 없거나 꺼져 있으면 검증만 건너뛰고 PDF는 그대로 만든다.

서버(DGX, tmux 안에서):

```bash
pip install -r requirements-train.txt && FORM_ADAPTER=outputs/qwen3vl4b-lora/adapter uvicorn serve:app --host 127.0.0.1 --port 8001
```

이 PC(터널을 열어 둔 채로):

```bash
ssh -L 8001:localhost:8001 dgx-spark
```

이 PC의 `.env`에 `FORM_VERIFIER_URL=http://localhost:8001`을 넣고 워커를 다시 켠다.

- 공유 서버라 `127.0.0.1`로만 연다. 신고서 이미지(상호·사업자번호·금액)가 서버로 가므로 실제 사용자 데이터로는 쓰지 않는다.
- 모델 정확도(신고서 1장 전체 일치 87.5%) 때문에 결과는 '확인 권장' 경고로만 보여준다.
- `vatform/fields.py`, `vatform/fill.py`는 앱의 `app/vat_form/`과 같은 내용이어야 한다. 한쪽을 고치면 다른 쪽도 맞춘다.

## 확인한 것 / 아직 안 한 것

- 이 PC에서 확인: 칸 좌표와 덧입히기 결과(샘플 이미지 육안 확인), 데이터 생성, 학습용 collator.
  collator는 Qwen3-VL processor로 돌려 답변 토큰만 학습되는 것을 확인했다. 이미지 한 장은 약 2,280 토큰, read 예시는 전체 약 3,000 토큰이다.
- 아직 안 함: GPU에서의 실제 학습·평가. 서버에서 `--smoke`부터 돌려 확인한다.
