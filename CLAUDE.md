# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 작업 규칙 (필수 준수)

1. **지시받은 것만 실행한다.** 지시한 작업이 막히거나 해결되지 않는다고 임의로 다른 방안·범위를 적용하지 않는다. 막히면 반드시 먼저 사용자에게 상황을 설명하고 질문한 뒤 다음 지시를 기다린다.
2. **코드는 최대한 간결하고 가독성 있게 작성한다.**
3. **커밋은 절대 직접 실행하지 않는다.** 커밋은 사용자가 직접 진행한다.
4. **현재 코드와 아래 기준 문서를 따르고, 임의로 벗어나지 않는다.** 다르게 진행해야 하는 경우는 사용자가 명시적으로 지시했을 때만 예외로 허용된다.

## 기준 문서

| 문서 | 성격 |
|---|---|
| `README.md` | 폴더 구조, 실행 방법, 주요 설정 |
| `requirements.txt` / `requirements-dev.txt` | 백엔드 패키지 버전의 기준 |
| `frontend/package.json` | 프론트엔드 패키지 버전의 기준 |

## Product summary

VAT-AI는 소상공인을 위한 부가가치세(VAT) 신고 지원 서비스의 프로토타입이다.

```
영수증·매출 정산서 사진 → OCR(CLOVA / Luna 사진 인식) → 거래 확정
   → 매입세액 공제 판별(LangGraph + 법령 RAG) → 세액 계산 → 신고서 PDF 생성·검증
```

외부 호출부는 교체 가능한 어댑터 계약 뒤에 둔다. OCR은 `app/receipts/ocr/contract.py`(`OCR_PIPELINE`), 공제 판별은 `app/deduction/analyzer.py`(`DEDUCTION_ANALYZER`)다.

## Stack

- **Backend**: Python 3.11+, FastAPI, SQLModel(+ SQLAlchemy 2), Alembic, Pydantic 2 / pydantic-settings, Uvicorn, LangGraph, OpenAI
- **DB**: PostgreSQL 16 + pgvector (`pgvector/pgvector:pg16` Docker 이미지)
- **인증**: `python-jose[cryptography]`(JWT), `bcrypt`(비밀번호 해싱 — passlib은 최신 bcrypt와 호환 문제로 제외)
- **Frontend**: React 19 + Vite + TypeScript, react-router-dom, axios

## 로컬 개발 환경

```bash
docker compose up -d db
source .venv/Scripts/activate      # Git Bash (.venv\Scripts\Activate.ps1 — PowerShell)
python -m pip install -r requirements-dev.txt
python -m alembic upgrade head
python -m uvicorn app.main:app --reload
python -m app.jobs.worker          # 별도 터미널: OCR·분석·PDF 작업자
python -m pytest
```

`.venv`는 이 컴퓨터에 종속적이라 git에 커밋하지 않는다.

## 폴더 구조

```
app/
├── main.py               앱 진입점, 라우터·CORS 등록
├── core/                 config.py(.env), database.py(엔진·세션·모델 import), security.py(JWT·해싱)
├── common/exceptions.py  공통 예외 핸들러
├── auth/                 /auth — 회원가입·로그인·/auth/me·비밀번호 재설정, get_current_user
├── business/             사업자 정보, 국세청 진위 확인(nts_client), 거래처 기억(merchant_memory)
├── receipts/             /receipts — 업로드·저장(storage)·목록, 상세(details)·확인 질문(questions)
│   └── ocr/              OCR 파이프라인: contract, luna(작업자 어댑터), ocr_client(CLOVA), luna_client, photo_ocr, line_structure 등
├── sales_monthly/        /sales/monthly — 월간 매출 정산서 인식·검토
├── transactions/         /v2/transactions — 거래 확정·수정·휴지통·세액 요약
├── deduction/            공제 판별: analyzer.py(계약), graph/(LangGraph), rag/(법령 임베딩·검색), /reports
├── vat_return/           engine.py(세액 계산), returns·fields·fill·render·verifier(신고서 PDF와 검증)
├── jobs/                 /v2/jobs — 비동기 작업 API와 worker.py
└── migrations/versions/  Alembic
frontend/                 React 앱 (src/api, components, pages, hooks, styles)
tests/                    pytest
data/laws.json            RAG 법령 원본 (app.deduction.rag.fetch_laws / load_laws)
training/                 신고서 칸 인식 모델 학습 코드와 검증 서버(serve.py)
```

새 SQLModel 모델을 추가하면 `app/core/database.py`의 import 목록에도 추가한다(Alembic autogenerate용).

## 구현 참고

- **엔티티 관계**: `User` 1—N `Receipt`, `Receipt` 1—1 `Deduction`. 거래는 `Transaction`(v2)으로 확정·관리한다. 리포트는 테이블이 아니라 집계 조회 응답이다.
- **인증 흐름**: JWT payload는 `{ sub: User.id, email }`. 토큰 검증 시 `sub`로 유저를 다시 조회한다(`get_current_user` Depends).
- **라우트 순서**: FastAPI는 선언 순서대로 매칭하므로 리터럴 경로를 path parameter 라우트보다 먼저 등록한다.
- **마이그레이션**: 새 리비전의 `down_revision`은 항상 현재 head를 가리키게 해서 head를 하나로 유지한다.

## 환경 변수

`.env.example`이 전체 목록이다. 핵심은 `DB_URL`, `JWT_SECRET`, `OPENAI_API_KEY`, `DEDUCTION_ANALYZER`, `OCR_PIPELINE`, `CLOVA_OCR_API_URL`, `CLOVA_OCR_SECRET_KEY`, `NTS_BUSINESS_API_KEY`, `FORM_VERIFIER_URL`이다. `CLOVA_API_KEY`는 기존 설정과의 호환을 위한 fallback이다.
