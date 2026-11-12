# VAT-AI — 소상공인을 위한 AI 부가가치세 신고 지원 서비스

영수증 사진 업로드 → OCR 인식 → 매입세액 공제 판별(LangGraph + RAG) → 부가세 신고서 PDF 생성까지 이어지는 프로토타입.

## 폴더 구조

```
app/                      FastAPI 백엔드
├── main.py               앱 진입점, 라우터·CORS 등록
├── core/                 설정(.env), DB 세션, JWT·비밀번호
├── common/               공통 예외 처리
├── auth/                 회원가입·로그인·비밀번호 재설정
├── business/             사업자 정보, 국세청 진위 확인, 거래처 기억
├── receipts/             영수증 업로드·저장·목록
│   └── ocr/              OCR 파이프라인(CLOVA, Luna 사진 인식, 구조 파싱)
├── sales_monthly/        월간 매출 정산서 인식·검토
├── transactions/         거래 확정·수정·휴지통·세액 요약
├── deduction/            매입세액 공제 판별
│   ├── analyzer.py       공제 판별 어댑터 계약
│   ├── graph/            LangGraph 분류 그래프
│   └── rag/              법령 임베딩·검색
├── vat_return/           세액 계산 엔진, 신고서 PDF 채우기·검증
├── jobs/                 비동기 작업(OCR·분석·PDF) API와 작업자
└── migrations/           Alembic 마이그레이션
frontend/                 React + Vite + TypeScript
tests/                    백엔드 테스트(pytest)
data/laws.json            RAG용 법령 조문 원본
docker/                   Postgres 초기화(pgvector)
storage/                  로컬 업로드 파일(git 제외)
training/                 신고서 칸 인식 모델 학습·검증 서버 코드
```

## 실행

### 1. DB (Docker)

```bash
docker compose up -d db
```

### 2. 백엔드

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1          # Git Bash: source .venv/Scripts/activate
python -m pip install -r requirements-dev.txt
copy .env.example .env              # 값 채우기
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

API 문서: http://localhost:8000/docs

### 3. 작업자 (OCR·분석·PDF)

API 서버와 별도 터미널에서 같은 `.env`로 실행한다.

```bash
python -m app.jobs.worker
```

### 4. 프론트엔드

```bash
cd frontend
copy .env.example .env              # VITE_API_URL=http://localhost:8000
npm install
npm run dev
```

웹: http://localhost:5173

### 5. 법령 데이터(RAG) 등록 — 최초 1회

```bash
python -m app.deduction.rag.load_laws      # data/laws.json → law_embeddings
python -m app.deduction.rag.fetch_laws     # 법령 개정 시 data/laws.json 갱신
```

## 주요 설정 (`.env`)

| 키 | 설명 |
|---|---|
| `DB_URL`, `JWT_SECRET` | DB 연결, JWT 서명 키 |
| `OPENAI_API_KEY` | 공제 판별·임베딩·Luna 인식 |
| `DEDUCTION_ANALYZER` | 공제 판별 어댑터. 예: `app.deduction.graph.adapter:create_analyzer` |
| `OCR_PIPELINE` | OCR 어댑터. 예: `app.receipts.ocr.luna:create_pipeline` |
| `CLOVA_OCR_API_URL`, `CLOVA_OCR_SECRET_KEY` | CLOVA OCR |
| `NTS_BUSINESS_API_KEY` | 국세청 사업자 상태 조회 |
| `FORM_VERIFIER_URL` | 신고서 검증 모델 서버(`training/serve.py`). 비우면 검증 생략 |

전체 목록은 `.env.example` 참고.

비밀번호 찾기의 이메일 인증 코드 흐름과 SMTP 설정은 [설정 가이드](docs/PASSWORD_RESET.md)를 참고한다.

## 테스트

```bash
python -m pytest
cd frontend && node --test tests/*.test.mjs
```
