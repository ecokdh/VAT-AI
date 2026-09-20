# VAT-AI

소상공인을 위한 부가가치세 신고 지원 서비스

## Track A — 인증(Auth) 구현 현황

### 구현 완료 항목
- `POST /auth/register` — 이메일/비밀번호 회원가입 (가입과 동시에 JWT 발급)
- `POST /auth/login` — 로그인, JWT 발급
- `GET /auth/me` — 현재 로그인한 사용자 정보 조회
- `app/auth/dependencies.py`의 `get_current_user` — 다른 트랙(Receipts, Deduction)이 그대로 `Depends(get_current_user)`로 재사용 가능
- 비밀번호는 bcrypt로 해싱하여 저장 (평문 저장 없음)
- 에러 응답은 `api-spec.md` §1.3 포맷(`{ "error": { "code", "message" } }`)으로 통일
- Alembic 마이그레이션으로 `users` 테이블 생성

### 기술 스택 (requirements.md 버전 고정 준수)
- FastAPI 0.141.1, SQLModel 0.0.42, Alembic 1.20.0
- python-jose (JWT), bcrypt (비밀번호 해싱)
- PostgreSQL 16 (pgvector 이미지, Docker)

### 실행 방법

```bash
# 1. 가상환경 세팅
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. DB 실행 (Docker)
docker run -d --name vatai-db -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=vatai -p 5432:5432 pgvector/pgvector:pg16

# 3. .env 설정
cp .env.example .env
# DB_URL, JWT_SECRET 값 채우기

# 4. DB 마이그레이션
alembic upgrade head

# 5. 서버 실행
uvicorn app.main:app --reload
```

서버 실행 후 `http://localhost:8000/docs`에서 API 문서 확인 가능.

### 검증 결과
- `pytest tests/test_auth.py -v` — 전체 통과 (회원가입 → 중복 이메일 409 → 로그인 → 잘못된 비밀번호 401 → 토큰 없이 조회 401 → 정상 조회 200 흐름 검증)
- 수동 curl 테스트로 아래 케이스 확인 완료
  | 케이스 | 기대 결과 | 확인 |
  |---|---|---|
  | 정상 회원가입 | 201 + access_token | ✅ |
  | 중복 이메일 가입 | 409 EMAIL_ALREADY_EXISTS | ✅ |
  | 필드 누락 요청 | 400 VALIDATION_ERROR | ✅ |
  | 정상 로그인 | 200 + access_token | ✅ |
  | 잘못된 비밀번호 | 401 INVALID_CREDENTIALS | ✅ |
  | 토큰 없이 /auth/me | 401 UNAUTHORIZED | ✅ |
  | 유효 토큰으로 /auth/me | 200 + 사용자 정보 | ✅ |
  | 조작된 토큰으로 /auth/me | 401 (서버 정상 처리) | ✅ |
- DB 직접 조회로 `password_hash` 컬럼이 bcrypt 해시(`$2b$...`)로만 저장되고 평문이 없음을 확인

### 참고
- `.gitignore`에 `venv/` 항목 누락돼 있던 것 발견하여 추가함 (기존에는 `.venv/`만 있었음)
- `app/common/exceptions.py`의 validation 에러 메시지에 로컬 파일 경로가 노출되던 문제 수정