# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 작업 규칙 (필수 준수)

1. **지시받은 것만 실행한다.** 지시한 작업이 막히거나 해결되지 않는다고 임의로 다른 방안·범위를 적용하지 않는다. 막히면 반드시 먼저 사용자에게 상황을 설명하고 질문한 뒤 다음 지시를 기다린다.
2. **코드는 최대한 간결하고 가독성 있게 작성한다.**
3. **커밋은 절대 직접 실행하지 않는다.** 커밋은 사용자가 직접 진행한다.
4. **문서 기준으로 행동하고, 문서와 다른 방향으로 임의로 벗어나지 않는다.** 문서와 다르게 진행해야 하는 경우는 사용자가 명시적으로 지시했을 때만 예외로 허용된다. 기준 문서는 아래 "문서 체계" 참고.

## 문서 체계

| 문서 | 성격 | 우선순위 |
|---|---|---|
| `Proposal/최종기획서_9조.pdf` | 제품 기획, 유즈케이스(UC-001~004), UML(유즈케이스/시퀀스/액티비티/클래스) 다이어그램, UI/UX 와이어프레임 | **함수/워크플로우 구조의 기준.** 언어(TS→Python)만 바뀌고 구조는 이 문서를 따른다. |
| `Proposal/AI캡스톤1_9조_최종기획_발표자료.pdf` | 위 기획서의 발표용 요약 슬라이드 | 참고용 (기획서와 동일 내용의 축약본) |
| `Proposal/VAT-AI 전체 코드 정리.md` | 예전 NestJS/TypeORM 구현 스펙 (모듈·엔티티·API 전체 명세) | **스택은 더 이상 유효하지 않음** (NestJS → FastAPI로 전환됨, 아래 참고). 다만 엔티티 필드, API 계약, 비즈니스 로직(공제 판단 흐름, 신고서 집계 로직 등)은 FastAPI로 이식할 때 참고 자료로 유효함. |
| `requirements.md` / `requirements.txt` | 현재 프로젝트 의존성 버전 | 패키지 버전의 기준 |

## Project status — 통합 프로토타입

AI 고도화(성능 최적화, RAG 정교화 등)는 이번 단계에서 제외하고, 로그인 → 영수증 업로드 → OCR → 공제 판별 → 리포트로 이어지는 **최소 플로우가 동작하는 프로토타입**을 만드는 단계다. GPT/CLOVA OCR 등 외부 API 호출부는 인터페이스로 감싸서(`ai_client.py`, `ocr_client.py`), 이후 단계에서 그 구현체만 교체할 수 있게 설계한다.

현재 저장소에는 FastAPI backend(Track A/B/C), Alembic migration, backend 테스트, React frontend(Track D)가 구현되어 있다. Track C backend는 실제 OpenAI 공제 판별과 리포트 API를 제공하며, Track C frontend 화면은 아직 목데이터를 사용한다.

### 트랙 구현 및 연동 상태

- **Track A — 백엔드 인프라**: 회원가입·로그인·`GET /auth/me`, JWT 검증, 공통 예외 처리, 설정이 구현되어 있다.
- **Track B — 데이터 파이프라인**: 영수증 업로드·로컬 저장·CLOVA OCR·목록/상세 API와 실패 처리 규약이 구현되어 있다.
- **Track C — AI 로직**: `Deduction` 엔티티, OpenAI 기반 `POST /receipts/{id}/analyze`, deduction upsert, `GET /reports?period=` 집계가 구현되어 있다.
- **Track D — 프론트엔드**: 인증과 영수증 흐름은 backend API를 사용한다. 분석·리포트 화면은 현재 목데이터를 사용한다.

**공통 인프라**: PostgreSQL 연결, CORS(프론트 도메인 허용), Swagger(OpenAPI) 자동 문서화 확인.

## Product summary

VAT-AI("TAX-AI")는 소상공인을 위한 부가가치세(VAT) 신고 지원 서비스. 핵심 파이프라인:

```
영수증 이미지 업로드 → Naver CLOVA OCR → 국세청(NTS) 사업자 진위 검증
   → LLM + RAG 매입세액공제 판단 → 부가세 신고서(PDF) 생성
```

## Stack (`requirements.md` 참고)

- **Backend**: Python 3.11+, FastAPI 0.141.1, SQLModel 0.0.42(+ SQLAlchemy 2.0.54), Alembic 1.20.0(마이그레이션), Pydantic 2.13.5 / pydantic-settings, Uvicorn(ASGI 서버)
- **DB**: PostgreSQL 16 + pgvector 확장 (`pgvector/pgvector:pg16` Docker 이미지)
- **인증**: `python-jose[cryptography]`(JWT), `bcrypt`(비밀번호 해싱 — passlib은 최신 bcrypt와 호환 문제로 제외)
- **외부 연동**: `openai`(GPT API), `httpx`(CLOVA OCR / NTS API 호출), `boto3`(AWS S3)
- **Frontend**: React 19.3.0 + Vite 8.3.0 + TypeScript 7.0.2, react-router-dom, axios

## 로컬 개발 환경

```bash
# 가상환경 활성화 (프로젝트 루트에 .venv 존재)
source .venv/Scripts/activate      # Git Bash
# .venv\Scripts\Activate.ps1       # PowerShell

# 의존성 설치/동기화 (pytest 포함)
python -m pip install -r requirements-dev.txt

# DB 마이그레이션, 개발 서버, 전체 테스트
python -m alembic upgrade head
python -m uvicorn app.main:app --reload
python -m pytest
```

`.venv`는 이 컴퓨터에 종속적이라 git에 커밋하지 않는다(`.gitignore` 처리됨). 다른 팀원은 각자 `python -m venv .venv && python -m pip install -r requirements-dev.txt`로 자기 가상환경을 만든다.

## 현재 폴더 구조

```
vat-ai-backend/
├── app/
│   ├── main.py                  # FastAPI 앱 진입점, 라우터 등록, CORS 설정
│   ├── core/                    # Track A가 우선 세팅
│   │   ├── config.py            # .env 설정 (Pydantic Settings)
│   │   ├── database.py          # SQLModel 엔진, 세션
│   │   └── security.py          # JWT 발급/검증, 비밀번호 해싱
│   ├── auth/                    # Track A — /auth/register, /auth/login, /auth/me
│   │   ├── router.py
│   │   ├── models.py            # User 엔티티
│   │   ├── schemas.py
│   │   ├── service.py
│   │   └── dependencies.py      # get_current_user → 다른 트랙에서 import
│   ├── receipts/                # Track B — /receipts
│   │   ├── router.py
│   │   ├── models.py            # Receipt 엔티티
│   │   ├── schemas.py
│   │   ├── service.py           # 업로드, S3 저장
│   │   └── ocr_client.py        # Clova OCR 호출 어댑터
│   ├── deduction/                # Track C — /receipts/{id}/analyze, /reports
│   │   ├── router.py
│   │   ├── models.py            # Deduction 엔티티
│   │   ├── schemas.py
│   │   ├── service.py
│   │   └── ai_client.py         # OpenAI GPT 공제 판별 호출 래퍼
│   ├── common/
│   │   ├── exceptions.py        # 공통 예외 핸들러
│   │   └── responses.py         # 공통 응답 포맷
│   └── migrations/               # Alembic
│       └── versions/
├── frontend/                     # Track D (React + Vite + TS)
├── tests/
│   ├── test_auth.py
│   ├── test_receipts.py
│   ├── test_deduction.py
│   └── test_migrations.py
├── .env.example
├── alembic.ini
└── requirements.txt
```

## 이전 NestJS 스펙 참고 (`Proposal/VAT-AI 전체 코드 정리.md` 기준)

아래 내용은 역사적 참고 자료다. 현재 구현·데이터 모델·API 계약은 `api-spec.md`와 현재 FastAPI 코드를 우선하며, 이 절의 원래 NestJS 구조로 되돌리지 않는다.

**모듈 ↔ FastAPI 라우터 대응**: `AuthModule`→`app/auth`, `ReceiptsModule`+`OcrModule`+`S3Module`→`app/receipts`, `ValidationModule`(국세청 사업자 진위 검증, 회원가입 시에도 재사용)→`app/auth` 또는 별도 `validation` 모듈, `RagModule`+`DeductionModule`→`app/deduction`, `ReportsModule`→`app/deduction`(또는 `reports`로 분리).

**현재 엔티티 관계**: `User` 1—N `Receipt`; `Receipt` 1—1 `Deduction`이다. `Report`는 테이블이 아니라 `Receipt`와 `Deduction`을 월별로 집계하는 조회 응답이다.

**인증 흐름**: JWT payload는 `{ sub: User.id, email }`. 토큰 검증 시 `sub`로 유저를 다시 조회해 현재 유저 컨텍스트를 만든다(FastAPI에서는 `get_current_user` Depends로 구현, 원본의 `@CurrentUser()` 데코레이터에 대응).

**현재 공제 판단 흐름**: 영수증의 상호·금액·OCR 원문을 OpenAI에 전달하고 구조화 응답의 `is_deductible`, `reason`, `category`를 파싱한다. 공제 가능 시 영수증 금액을 `amount`로 저장하고, 같은 영수증의 기존 판별 결과는 upsert로 갱신한다.

**라우트 순서 주의**: 원본 스펙에서 `GET /deduction/user/summary`, `GET /deduction/refund-date`가 `GET /deduction/{receipt_id}`보다 먼저 선언되어야 했던 것처럼, FastAPI도 라우트를 선언 순서대로 매칭하므로 리터럴 경로를 path parameter 라우트보다 먼저 등록해야 한다.

## 환경 변수

현재 backend는 `DB_URL`, `JWT_SECRET`, `OPENAI_API_KEY`, `CLOVA_OCR_API_URL`, `CLOVA_OCR_SECRET_KEY`를 사용한다. `CLOVA_API_KEY`는 기존 설정과의 호환을 위한 fallback이다.

전체 기능 구현 시 원본 스펙 기준으로 추가 필요: `AWS_REGION`/`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`AWS_S3_BUCKET`(S3 업로드), `NTS_API_KEY`/`NTS_API_URL`(국세청 사업자 진위 검증), `EMBEDDING_MODEL`(RAG 임베딩), `ADMIN_API_KEY`(RAG 법령 임베딩 등록용 관리자 보호 라우트).
