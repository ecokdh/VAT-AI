#!/usr/bin/env bash
# start_all.sh로 띄운 모델 서버 3개를 끈다. 요청 처리 중 멈춰 일반 종료가 안 되는 서버도 강제로 정리한다.
#   bash ~/vat-ai-dong/training/stop_all.sh
for name in form judge ocr serve; do  # serve: 예전에 공제 서버를 띄우던 세션 이름
  tmux kill-session -t "$name" 2>/dev/null && echo "$name: 세션 종료"
done
sleep 3
# 이 계정에서 우리 서버 파일로 띄운 uvicorn만 골라 남은 것을 강제 종료한다.
pkill -9 -u "$USER" -f "uvicorn (serve|serve_slm|serve_receipt_ocr):app" && echo "남아 있던 서버 프로세스를 강제 종료했습니다."
ss -ltn | grep -E "127.0.0.1:800[123] " || echo "8001·8002·8003 모두 비어 있습니다."
