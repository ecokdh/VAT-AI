# OCR·Luna 병행 영수증 인식 개선

## 이번 변경

- 사진과 네이버 일반 OCR 전체 토큰(글자·좌표·신뢰도·줄바꿈)을 함께 Luna low에 전달합니다.
- 주소·전화·결제수단·승인번호·문서번호를 상세 결과에 연결합니다. 번호는 문자열로 보존합니다.
- 소계는 지원하는 라벨이 OCR에 있는 경우에만 채택합니다. 합계·결제액을 소계로 복사하지 않습니다. 근거 부족은 null로 보류하고 후보·원출력은 남깁니다. 이것이 인쇄 없음 판정을 뜻하지는 않습니다.
- 사진·네이버 원응답·모델 원응답·추출값·사용자 수정값을 분리합니다. 기존 품목의 raw_name은 서버가 원본 행에서 복원하며, 신규 행에는 모델 원문을 만들지 않습니다.
- 기본 6개 필드와 품목명을 바로 수정하고, ‘전체 정보 확인’에서 전체 금액·품목·증빙 정보를 확인합니다.
- 사업 프로필과 규칙 기반 용도 질문을 사용합니다. 미응답 저장은 허용하지만 필요한 답변이 없으면 공제 분석을 보류합니다.

## 실행

Python과 Node.js가 필요합니다. 이 저장소 자체의 가상환경을 사용하며 실험 저장소는 필요 없습니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
# .env에서 DB_URL, JWT_SECRET, OPENAI_API_KEY, CLOVA 설정 등을 채웁니다.
# 새 DB 또는 변경 검토를 마친 DB에 적용합니다. 기존 DB는 먼저 백업하세요.
.\.venv\Scripts\python.exe -m alembic upgrade head
cd frontend
npm ci
cd ..
powershell -ExecutionPolicy Bypass -File scripts/start_luna_local.ps1
```

프런트엔드: http://127.0.0.1:18786 · API: http://127.0.0.1:18785/docs
시작 스크립트는 DB를 초기화하거나 환경파일을 덮어쓰지 않습니다. 워커도 함께 실행합니다. `.env.luna.local`이 존재하면 `.env`보다 우선하므로 기존 사용자 설정을 확인하세요.

## 주요 설정

| 설정 | 내용 |
| --- | --- |
| `OCR_PIPELINE` | `app.ocr_pipeline.luna:create_pipeline` |
| `RECEIPT_RECOGNITION_BACKEND` | `luna_low` |
| `LUNA_INPUT_MODE` | 기본 `photo_ocr`. `photo`는 명시적인 기존 사진 단독 모드 |
| `CLOVA_OCR_API_URL` | General OCR Invoke URL |
| `CLOVA_OCR_SECRET_KEY` | Secret Key. 기존 `CLOVA_API_KEY` 별칭 지원 |
| `OPENAI_API_KEY` / `LUNA_API_KEY_FILE` | 키 직접 설정 또는 외부 dotenv 파일 경로 |
| `LUNA_BUDGET_KRW` | 누적 모델 비용 추정 상한. 기존 원장의 더 낮은 상한도 유지 |
| `LUNA_BUDGET_LEDGER_FILE` | 실제 usage 정산 및 미확정 비용 예약 원장 |
| `LUNA_TIMEOUT_SECONDS` | OCR·토큰 확인·생성을 포함한 전체 제한 |
| `DB_URL` / `STORAGE_DIR` | 거래 DB / 원본 사진 저장소 |

모델은 기존 검증 계약의 `gpt-6-luna`, 추론 `low`를 사용합니다. 사전 토큰 확인과 단일 실행 잠금을 유지합니다. OCR 실패 시 Luna 단독 경로로 전환하지 않으며 자동 재시도하지 않습니다. 모델 생성 실패 후에도 확보한 OCR 응답은 오류 결과에 보존합니다.

OpenAI 비용은 설정된 비교용 단가·환산값으로 계산하는 추정치입니다. 네이버 요청은 원장 `ocr_attempts`에 별도로 기록하며 비용 미확정은 null입니다. 네이버 과금은 OpenAI 비용 상한에 포함되지 않습니다. 토큰 확인 뒤 예산이 부족하면 모델 생성은 중단되지만 앞서 실행된 OCR에는 과금될 수 있습니다.

## 데이터와 검증 범위

기존 DB·사진·정답을 자동 변경하거나 평가 자료를 서비스 입력에 주입하지 않습니다. DB와 원본 사진은 별도 저장소이므로 팀원 공동 사용에는 둘 다 공유 가능한 서버 설정이 필요합니다. 로컬 Docker DB만으로 원격 팀원에게 자동 공유되지 않습니다.

개발용 30장 재평가와 단위·통합 테스트는 서로 다른 검증입니다. 의미 동일·사용자 수정 정답을 적용한 재평가 점수를 순수 OCR 인식률이나 독립 데이터 정확도로 표현하지 않습니다. 실제 소계가 있는 새로운 영수증과 외부 API 장애·청구 내역은 별도 운영 검증이 필요합니다.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm run build
```

## 커밋 전 검증 (2026-10-18)

- 백엔드 전체 테스트 265개, 프런트엔드 회귀 테스트 5개와 TypeScript/Vite 빌드 통과.
- 사진 업로드→워커→OCR·모델 어댑터→수정→거래 저장→보관함 재조회는 격리 DB와 모의 외부 응답으로 검증.
- 실제 외부 호출 1건에서 General OCR 1회와 Luna 생성 1회 성공. 총 21.4초, 모델 사용량 환산 약 3.87원(네이버 요금 별도·미확정). 전체 데이터 정확도 재측정 결과는 아님.
- 기존 저장 자료를 사용해 기본·상세 편집값 유지와 모바일/데스크톱 표시를 확인. 화면 검수의 임시 수정은 저장하지 않음.
- 키·DB·실험 응답·사진은 공유 코드에 포함하지 않음. 검증 과정에서 푸시·PR 변경은 수행하지 않음.
