# 영수증 문서 인식·거래 검토 프로토타입

사진 업로드 → Luna low 문서 인식 → 문서 종류·판독 문제 확인 → 기본 6개 필드 수정 → 전체 상세정보 확인 → 거래 저장 순서입니다. 필요한 경우 재촬영을 안내합니다. 사업 프로필과 규칙 기반 사용 목적 질문을 제공하며, 사용자 답변만으로 공제 여부를 확정하지 않습니다.

## 실행

기준 코드는 `track-fullstack`의 `630218a`입니다. 기존 로그인·거래·공제 분석 경로는 유지합니다.

1. Python 가상환경에서 `pip install -r requirements.txt`를 실행합니다.
2. `.env.example`을 `.env`로 복사하고 DB·JWT·API 설정을 채웁니다. Luna 경로 설정은 아래와 같습니다.

```ini
OPENAI_API_KEY=<개인 키>
RECEIPT_RECOGNITION_BACKEND=luna_low
OCR_PIPELINE=app.ocr_pipeline.luna:create_pipeline
LUNA_TIMEOUT_SECONDS=180
LUNA_BUDGET_KRW=2000
LUNA_BUDGET_LEDGER_FILE=storage/luna_budget.json
```

로컬 빈 DB로 확인하려면 `DB_URL=sqlite:///./vat_ai.db`를 사용합니다. `.env`와 DB는 커밋하지 않습니다. 기존 DB는 백업 후 마이그레이션하세요. 별도 로컬 실험 DB는 이 공유본으로 자동 이전하지 않습니다.

3. `alembic upgrade head`를 실행합니다.
4. API와 워커를 각각 실행합니다.

```text
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
python -m app.jobs.worker
```

5. `frontend`에서 `npm ci`, `npm run dev`를 실행합니다. 프런트엔드 `.env.local`에 `VITE_API_URL=http://localhost:8000`을 설정합니다. 기본 허용 프런트 주소는 `http://localhost:5173`이며 다른 주소는 `LOCAL_FRONTEND_ORIGIN`으로 추가합니다.

## 동작과 범위

- `gpt-6-luna`, 추론 `low`를 사용합니다. 문서 분류를 같은 인식 요청에 포함하며 자동 유료 재시도나 다른 유료 OCR fallback은 없습니다.
- 원본 사진·모델 원출력·사용자 확인 결과를 분리합니다. 품목 원출력 이름과 인쇄 금액 부호를 보존하며 VAT·단가를 계산해서 채우지 않습니다.
- 기본 화면은 상호·사업자번호·품목·공급가액·VAT·날짜를 보여줍니다. 전체 화면과 거래 상세정보에는 금액 역할·모든 품목·수량·단가·할인·옵션 연결을 표시합니다.
- 개인사업자·법인은 사업 프로필에서 받고 거래에는 실제 사용 목적을 묻습니다. 미응답 저장은 허용하되 필요한 정보가 부족하면 공제 분석을 보류합니다. 혼합 지출은 품목별 용도를 기록하며 자동 공제 금액 배분은 하지 않습니다.
- 인식 실패와 미지원 문서를 구분합니다. 판단이 불확실하거나 일부 정보만 읽히면 검토 경로로 보냅니다.
- 사진·DB·계정·실험 자료·팀 테스트 자료 기능은 포함하지 않습니다. 이 브랜치를 받는 것만으로 공유 서버나 영수증 50건이 제공되지는 않습니다.

Luna 호출에는 비용이 발생합니다. 예산 원장은 실제 사용량과 미확정 예약액을 합산해 다음 요청을 제한하며, OpenAI 계정 전체 비용을 제한하는 기능은 아닙니다. 한 번에 한 요청을 처리하는 프로토타입입니다. 실서비스 배포·대규모 동시 요청은 별도 작업입니다.

## 검증

```text
python -m pytest -q
cd frontend
npm run build
```

테스트는 독립적인 가상 응답과 임시 DB를 사용합니다. 실제 촬영 결함 판별 정확도나 공제 판단의 정확도를 보장하는 테스트는 아닙니다.
