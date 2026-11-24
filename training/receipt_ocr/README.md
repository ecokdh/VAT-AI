# 매입 영수증 Qwen OCR 서버

팀원이 캐글에서 학습한 LoRA 두 개를 DGX에서 OpenAI 호환 API로 연다. 앱의 `app/receipts/ocr/qwen.py`(track-ocr 브랜치)가 호출한다.

| 앱 경로 | 요청 model 이름 | 기반 모델 + 어댑터 |
|---|---|---|
| `qwen_ocr` | `vat-receipt-qwen-ocr` | Qwen/Qwen3-4B-Instruct-2507 + `qwen3-4b-ocr-adapter` |
| `qwen_photo_ocr` | `vat-receipt-qwen-vl-step087` | Qwen/Qwen3-VL-8B-Instruct + `qwen3-vl-8b-photo-ocr-adapter` |

## DGX에 올리기

VS Code Remote-SSH 탐색기로 올린다.

```
~/vat-ai-dong/models/qwen3-4b-ocr-adapter/          (어댑터 폴더 그대로, training_args.bin은 필요 없음)
~/vat-ai-dong/models/qwen3-vl-8b-photo-ocr-adapter/
~/vat-ai-dong/training/receipt_ocr/serve_receipt_ocr.py
```

## 실행

메모리를 먼저 본다(공제 sLLM 약 9GB + 4B 약 8GB + 8B-VL 약 17GB). 처음 실행 때 Qwen3-VL-8B(약 17GB)를 내려받는다.

```bash
free -h
```

```bash
tmux new -d -s ocr -c ~/vat-ai-dong/training/receipt_ocr "HF_HOME=$HOME/vat-ai-dong/hf-cache $HOME/vat-ai-dong/.venv/bin/uvicorn serve_receipt_ocr:app --host 127.0.0.1 --port 8003"
```

- 한쪽만 올리려면 앞에 `OCR_LOAD=text` 또는 `OCR_LOAD=photo`를 붙인다.
- 상태 보기: `tmux attach -t ocr` (빠져나오기 `Ctrl+B` → `D`), 끄기: `tmux kill-session -t ocr`
- VS Code '포트' 탭에 8003이 전달되면 이 PC의 `localhost:8003`으로 닿는다.

## 앱 연결 (이 PC `.env`, track-ocr 병합 후)

```
QWEN_OCR_BASE_URL=http://localhost:8003/v1
QWEN_PHOTO_OCR_BASE_URL=http://localhost:8003/v1
```

모델 이름은 앱 기본값(`QWEN_OCR_MODEL`, `QWEN_PHOTO_OCR_MODEL`)과 같으므로 따로 넣지 않는다.
서버가 꺼져 있으면 앱은 Qwen 경로를 실패로 보고 Luna로 대체한다.
