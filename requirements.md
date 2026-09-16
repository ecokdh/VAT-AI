# VAT-AI 스켈레톤 — 필요 언어 및 프레임워크 (버전 고정)

모든 버전은 PyPI/npm의 현재 최신 배포본이며, `pip install --dry-run` / `npm install --dry-run`으로 아래 조합 전체를 함께 설치했을 때 **의존성 충돌이 없음을 실제로 검증**했다.

## 런타임

| 항목 | 버전 | 비고 |
|---|---|---|
| Python | 3.11+ | 이 환경에서 3.13.14로 검증 완료 |
| Node.js | ^20.19.0 또는 >=22.12.0 | Vite 8의 최소 요구사항. 이 환경에서 v24.21.0으로 검증 완료 |
| PostgreSQL | 16 | pgvector 확장 포함 (`pgvector/pgvector:pg16` Docker 이미지 사용) |

## Backend — Python / FastAPI (`requirements.txt`)

| 패키지 | 버전 | 용도 |
|---|---|---|
| `fastapi` | 0.141.1 | 웹 프레임워크 |
| `uvicorn[standard]` | 0.53.0 | ASGI 서버 |
| `sqlmodel` | 0.0.42 | 엔티티 정의 + API 스키마 (TypeORM 엔티티 대응) |
| `sqlalchemy` | 2.0.54 | SQLModel의 기반 ORM (명시적 버전 고정) |
| `alembic` | 1.20.0 | DB 마이그레이션 |
| `pydantic` | 2.13.5 | 데이터 검증 (FastAPI/SQLModel 공통 의존성) |
| `pydantic-settings` | 2.15.0 | `.env` 기반 설정 관리 |
| `email-validator` | 2.3.0 | Pydantic `EmailStr` 검증 (auth 스키마의 이메일 필드용) |
| `psycopg2-binary` | 2.9.13 | PostgreSQL 드라이버 |
| `python-jose[cryptography]` | 3.5.0 | JWT 발급/검증 |
| `bcrypt` | 5.0.0 | 비밀번호 해싱 (passlib은 bcrypt 4.1+와 호환 문제가 있어 제외, bcrypt 직접 사용) |
| `python-multipart` | 0.0.32 | 파일 업로드(영수증 이미지) 파싱 |
| `boto3` | 1.43.95 | AWS S3 업로드 |
| `openai` | 3.14.1 | GPT API 호출 (AI 로직 인터페이스 내부 구현체) |
| `httpx` | 0.28.1 | CLOVA OCR / 국세청(NTS) API 호출 |
| `pgvector` | 0.5.0 | pgvector 컬럼 타입 (SQLAlchemy/SQLModel 연동) |
| `python-dotenv` | 1.2.3 | 로컬 `.env` 로드 |

## Frontend — React + Vite + TypeScript (`package.json`)

| 패키지 | 버전 | 구분 |
|---|---|---|
| `react` | 19.3.0 | dependency |
| `react-dom` | 19.3.0 | dependency |
| `react-router-dom` | 7.18.4 | dependency |
| `axios` | 1.20.0 | dependency |
| `vite` | 8.3.0 | devDependency |
| `typescript` | 7.0.2 | devDependency |
| `@vitejs/plugin-react` | 6.1.1 | devDependency |
| `@types/react` | 19.3.0 | devDependency |
| `@types/react-dom` | 19.3.0 | devDependency |
| `@types/node` | 22.20.3 | devDependency |

## 검증 방법

- Backend: 위 16개 패키지를 한 번에 `pip install --dry-run`으로 설치 시도 → resolver 에러 없이 전체 설치 계획 산출 확인.
- Frontend: 위 10개 패키지를 한 번에 `npm install --dry-run`으로 설치 시도 → peer dependency 경고/에러 없이 57개 패키지 설치 계획 산출 확인.
