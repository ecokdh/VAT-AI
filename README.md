# VAT-AI B트랙

## B트랙이 하는 일

B트랙은 로그인한 사용자의 영수증을 처리합니다.

- 영수증 이미지 업로드
- 이미지 형식·내용·크기 검증 및 로컬 저장
- CLOVA OCR 응답과 추출 결과 저장
- 본인 영수증 목록·상세 조회

현재 업로드 검증은 JPEG/PNG를 대상으로 합니다.

## 설치와 실행

아래 명령은 저장소 루트에서 실행합니다. Python 3.11 이상이 필요합니다.

Windows(PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
python -m uvicorn app.main:app --reload
```

macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
python -m uvicorn app.main:app --reload
```

Swagger UI: <http://127.0.0.1:8000/docs>

`.env.example`을 `.env`로 복사한 뒤 환경에 맞는 값을 입력합니다. `.env`에는 실제 비밀값을 넣되 Git에 커밋하지 않습니다.

## 환경변수

| 변수 | 용도 |
| --- | --- |
| `DB_URL` | 사용자·영수증을 저장할 데이터베이스 연결 URL |
| `JWT_SECRET` | 로그인 토큰 서명 키 |
| `OPENAI_API_KEY` | 기존 프로젝트의 AI 설정값이며 B트랙 OCR 호출에는 사용하지 않음 |
| `CLOVA_OCR_API_URL` | 호출할 CLOVA OCR Template V2 `/infer` endpoint |
| `CLOVA_OCR_SECRET_KEY` | CLOVA OCR 인증 키 |
| `CLOVA_API_KEY` | 기존 설정과의 호환을 위한 인증 키 fallback |
| `STORAGE_DIR` | 업로드 파일을 저장할 디렉터리 |
| `MAX_UPLOAD_SIZE_BYTES` | 업로드 파일 크기 제한 |
| `MAX_IMAGE_PIXELS` | 이미지 픽셀 수 제한 |
| `CLOVA_TIMEOUT_SECONDS` | OCR 요청 timeout(초) |

OCR 코드가 포함되어 있다는 것과 실제 CLOVA 계정·endpoint·키·템플릿이 준비되어 있다는 것은 다릅니다. 이 저장소에는 실제 비밀값을 포함하지 않습니다.

## 주요 API

먼저 `POST /auth/register` 또는 `POST /auth/login`으로 토큰을 받은 뒤 `Authorization: Bearer <token>` 헤더를 사용합니다.

| 기능 | 주소 | 인증 |
| --- | --- | --- |
| 업로드 | `POST /receipts` | 필요 |
| 목록 | `GET /receipts` | 필요 |
| 상세 | `GET /receipts/{receipt_id}` | 필요 |

업로드 요청은 `multipart/form-data`의 파일 필드 이름을 `file`로 사용합니다. 응답이 HTTP 201이어도 `status=failed`이면 OCR 처리에 실패한 영수증입니다. `image_url`은 저장 키이며, 바로 열리는 공개 이미지 URL을 뜻하지 않습니다.

## 테스트

저장소 루트에서 실행합니다.

```powershell
python -m pytest -q
```

테스트는 mock OCR과 임시 SQLite·임시 파일 저장소를 사용합니다. 따라서 테스트 통과는 실제 CLOVA OCR API나 공유 PostgreSQL 연결 검증과 다릅니다.

## 현재 제한

- A트랙과 공통 인증·설정·예외 처리 및 migration 체인의 통합이 필요합니다. 이 브랜치는 A트랙과 최종 통합된 상태를 의미하지 않습니다.
- B트랙 migration은 `users` 테이블이 먼저 있어야 하며 현재 독립적으로 `alembic upgrade head`를 실행할 수 있는 완성된 공통 migration 체인이 아닙니다.
- 실제 CLOVA OCR 계정/API 호출, PostgreSQL 연결, 프론트엔드 연동은 이 브랜치에서 확인하지 않았습니다.
- `image_url` 접근 권한·다운로드 API 계약은 별도 통합이 필요합니다.
