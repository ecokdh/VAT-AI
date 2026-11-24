#!/usr/bin/env bash
# 앱이 쓰는 DGX 모델 서버 3개를 각각 tmux 세션으로 띄운다. 이미 떠 있는 세션은 건너뛴다.
#   bash ~/vat-ai-dong/training/start_all.sh
# 끄기: bash ~/vat-ai-dong/training/stop_all.sh
ROOT="$HOME/vat-ai-dong"

start() {  # 세션 이름, 폴더, 포트, uvicorn 앱
  local name=$1 dir=$2 port=$3 app=$4
  if tmux has-session -t "$name" 2>/dev/null; then echo "$name: 이미 실행 중 (포트 $port)"; return; fi
  if ss -ltn | grep -q "127.0.0.1:$port "; then
    echo "$name: 포트 $port를 다른 프로세스가 쓰고 있어 건너뜀 → stop_all.sh 실행 후 다시 시도"; return
  fi
  tmux new -d -s "$name" -c "$dir" \
    "HF_HOME=$ROOT/hf-cache $ROOT/.venv/bin/uvicorn $app --host 127.0.0.1 --port $port 2>&1 | tee $name.log"
  echo "$name: 시작 (포트 $port, 로그 $dir/$name.log)"
}

start form  "$ROOT/training"             8001 serve:app              # 신고서 PDF 검증 (Qwen3-VL-4B)
start judge "$ROOT/training/deduction"   8002 serve_slm:app          # 공제 판정 sLLM (Qwen3-4B)
start ocr   "$ROOT/training/receipt_ocr" 8003 serve_receipt_ocr:app  # 매입 OCR (Qwen3-4B, Qwen3-VL-8B)

echo "모델을 불러오는 데 1~3분 걸립니다. 준비 확인(각각 'Uvicorn running'이 보이면 완료):"
echo "  tail -n 2 $ROOT/training/form.log $ROOT/training/deduction/judge.log $ROOT/training/receipt_ocr/ocr.log"
echo "VS Code '포트' 탭에 8001·8002·8003이 전달됐는지도 확인하세요."
