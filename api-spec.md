# VAT-AI — DB 스키마 & API 명세 (v1)

이 문서는 `Proposal/최종기획서_9조.pdf`(구조/워크플로우 기준)를 바탕으로 4개 트랙이 공유하는 현재 API 계약이다. 여기 적힌 필드명·타입·경로·응답 형식은 임의로 바꾸지 말고, 바꿔야 하면 먼저 이 문서를 고친 뒤 코드를 맞춘다.

범위는 초기 프로토타입 플로우의 6단계 해피패스 + 최소 에러 처리(통일된 에러 응답, OCR 실패 상태 기록)까지다. 실패 전용 화면, 재시도, RAG, PDF 신고서 생성 등은 이번 스펙에 없다.

---

## 0. 설계 결정 사항 (체크리스트에 명시 안 돼 있어 이번에 확정한 것)

체크리스트가 필드명만 주고 타입/관계/포맷까지는 정하지 않은 부분들이다. 아래처럼 확정했으니, 다르게 가고 싶으면 여기부터 고쳐야 한다.

| 항목 | 결정 |
|---|---|
| `User.id` 타입 | UUID (최종기획서의 JWT `sub` 관례를 따름) |
| `Receipt.id`, `Deduction.id` 타입 | 정수 자동증가 (최종기획서 관례) |
| `Receipt.status` 값 | `"done"` \| `"failed"` 2가지만. OCR 호출은 업로드 요청 안에서 동기로 처리하므로 `"pending"` 상태는 없음 |
| OCR 실패 시 HTTP 응답 | 요청 자체는 `201 Created`로 성공 처리하고, 응답 바디의 `status="failed"`로만 실패를 표시 (추출 필드는 전부 `null`). 별도 재시도 엔드포인트는 이번 스프린트에 없음 |
| `Receipt` ↔ `Deduction` 관계 | 1:1. `analyze`를 다시 호출하면 기존 판별 결과를 덮어씀(upsert) — 원본 스펙의 1:N(재판별 이력 보존)은 다음 단계로 미룸 |
| `Deduction.category` | 고정 enum 없음. GPT가 생성하는 자유 문자열 |
| 공통 에러 응답 포맷 | `{ "error": { "code": string, "message": string } }` (아래 1.3 참고) |
| `POST /auth/register` 응답 | 가입과 동시에 로그인 처리하여 `access_token` 포함 (최종기획서의 register 동작과 동일 구조) |
| `GET /reports` period 포맷 | `YYYY-MM` (월 단위) |

---

## 1. 공통 규격

### 1.1 인증
JWT Bearer. `POST /auth/login`, `POST /auth/register` 를 제외한 모든 엔드포인트는 헤더가 필요하다.

```
Authorization: Bearer <access_token>
```

토큰 payload: `{ "sub": "<User.id>", "email": "<User.email>" }`. 검증 실패 시 `401 UNAUTHORIZED`.

### 1.2 공통 응답 헤더
`Content-Type: application/json` (파일 업로드 요청 제외).

### 1.3 에러 응답 포맷 (모든 엔드포인트 공통)

```json
{
  "error": {
    "code": "EMAIL_ALREADY_EXISTS",
    "message": "이미 가입된 이메일입니다."
  }
}
```

| HTTP | code | 발생 상황 |
|---|---|---|
| 400 | `VALIDATION_ERROR` | 요청 바디/쿼리 파라미터가 스키마와 안 맞음 |
| 401 | `UNAUTHORIZED` | 토큰 없음/만료/위조 |
| 401 | `INVALID_CREDENTIALS` | 로그인 이메일/비밀번호 불일치 |
| 404 | `NOT_FOUND` | 존재하지 않거나 본인 소유가 아닌 리소스 접근 |
| 409 | `EMAIL_ALREADY_EXISTS` | 회원가입 시 이메일 중복 |
| 502 | `EXTERNAL_API_ERROR` | GPT/CLOVA 호출 자체가 실패(타임아웃, 인증 오류 등). 단, OCR 실패는 §0 결정대로 `Receipt.status="failed"`로만 기록하고 이 코드는 쓰지 않음. 이 코드는 `POST /receipts/{id}/analyze`에서 GPT 호출이 실패했을 때만 사용 |

---

## 2. DB 스키마

```
User (users)
 └─< Receipt (receipts)        [1:N, receipts.user_id → users.id]
       └─1 Deduction (deductions)  [1:1, deductions.receipt_id → receipts.id, UNIQUE]
```

`Report`는 테이블이 아니라 `Receipt` + `Deduction`을 기간으로 묶어 합산하는 조회 전용 쿼리다.

### 2.1 `users`

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `id` | UUID | PK, default `gen_random_uuid()` | JWT `sub`로 사용 |
| `email` | varchar | UNIQUE, NOT NULL | 로그인 아이디 |
| `password_hash` | varchar | NOT NULL | bcrypt 해시 (평문 저장 금지) |
| `name` | varchar | NOT NULL | 사용자 이름 |
| `created_at` | timestamptz | NOT NULL, default now() | |

### 2.2 `receipts`

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `id` | serial | PK | |
| `user_id` | UUID | FK → `users.id`, NOT NULL | |
| `image_url` | varchar | NOT NULL | S3(또는 로컬) 저장 경로 |
| `ocr_raw` | text | NULL 허용 | CLOVA OCR 원문. `status="failed"`면 NULL |
| `vendor` | varchar | NULL 허용 | OCR 추출 상호명 |
| `amount` | float | NULL 허용 | OCR 추출 금액(합계) |
| `date` | date | NULL 허용 | OCR 추출 거래일자 |
| `status` | varchar(10) | NOT NULL, `"done"` \| `"failed"` | |
| `created_at` | timestamptz | NOT NULL, default now() | 목록 정렬 기준 |

### 2.3 `deductions`

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `id` | serial | PK | |
| `receipt_id` | integer | FK → `receipts.id`, UNIQUE, NOT NULL | 1:1 |
| `is_deductible` | boolean | NOT NULL | |
| `reason` | text | NOT NULL | GPT가 생성한 판단 근거 |
| `category` | varchar | NOT NULL | GPT가 생성한 자유 카테고리명 |
| `amount` | float | NOT NULL | 공제 가능 금액 |
| `created_at` | timestamptz | NOT NULL, default now() | |

---

## 3. API 명세

### 3.1 Track A — 인증

#### `POST /auth/register`
- 인증: 불필요
- Request body
  ```json
  { "email": "owner@shop.com", "password": "plain-text-pw", "name": "김대표" }
  ```
- Response `201 Created`
  ```json
  {
    "access_token": "eyJ...",
    "user": { "id": "uuid", "email": "owner@shop.com", "name": "김대표", "created_at": "2026-09-16T09:00:00Z" }
  }
  ```
- 에러: `409 EMAIL_ALREADY_EXISTS`, `400 VALIDATION_ERROR`

#### `POST /auth/login`
- 인증: 불필요
- Request body: `{ "email": "...", "password": "..." }`
- Response `200 OK`: `POST /auth/register`와 동일한 `{ access_token, user }` 형태
- 에러: `401 INVALID_CREDENTIALS`

#### `GET /auth/me`
- 인증: 필요
- Response `200 OK`
  ```json
  { "id": "uuid", "email": "owner@shop.com", "name": "김대표", "created_at": "2026-09-16T09:00:00Z" }
  ```
- 에러: `401 UNAUTHORIZED`

---

### 3.2 Track B — 영수증 / OCR

#### `POST /receipts`
- 인증: 필요
- Request: `multipart/form-data`, 필드 `file` (이미지)
- 동작: 이미지를 저장(S3/로컬) → CLOVA OCR 동기 호출 → 성공 시 `vendor`/`amount`/`date`/`ocr_raw` 채워서 `status="done"`, 실패 시 전부 `null`에 `status="failed"`로 저장
- Response `201 Created` (성공/실패 모두 이 형태, `status` 필드로 구분)
  ```json
  {
    "id": 12,
    "user_id": "uuid",
    "image_url": "https://.../receipts/12.jpg",
    "ocr_raw": "스타벅스 강남점 ...",
    "vendor": "스타벅스 강남점",
    "amount": 4500,
    "date": "2026-09-15",
    "status": "done",
    "created_at": "2026-09-16T09:10:00Z"
  }
  ```
- 에러: `400 VALIDATION_ERROR`(파일 누락/형식 오류), `401 UNAUTHORIZED`

#### `GET /receipts`
- 인증: 필요
- 동작: 현재 사용자 소유 영수증만, `created_at DESC`
- Response `200 OK`
  ```json
  [
    { "id": 12, "vendor": "스타벅스 강남점", "amount": 4500, "date": "2026-09-15", "status": "done", "created_at": "2026-09-16T09:10:00Z" }
  ]
  ```

#### `GET /receipts/{id}`
- 인증: 필요
- Response `200 OK`: `POST /receipts` 응답과 동일한 전체 필드
- 에러: `404 NOT_FOUND`(존재하지 않거나 타인 소유)

---

### 3.3 Track C — 공제 판별 / 리포트

#### `POST /receipts/{id}/analyze`
- 인증: 필요
- Request body: 없음
- 동작: 해당 영수증 정보를 `ai_client.py`(GPT 호출 인터페이스)로 전달 → 공제 여부 판별 → `deductions` upsert(기존 있으면 덮어씀)
- Response `200 OK`
  ```json
  {
    "id": 7,
    "receipt_id": 12,
    "is_deductible": true,
    "reason": "업무용 회의 목적의 음료 구매로 매입세액공제 대상입니다.",
    "category": "복리후생비",
    "amount": 4500,
    "created_at": "2026-09-16T09:12:00Z"
  }
  ```
- 에러: `404 NOT_FOUND`(영수증 없음), `502 EXTERNAL_API_ERROR`(GPT 호출 실패)

#### `GET /reports?period=YYYY-MM`
- 인증: 필요
- Query: `period` (예: `2026-09`, 필수)
- 동작: 현재 사용자의 `receipts.date`가 해당 월에 속하고 `deductions.is_deductible=true`인 건만 합산
- Response `200 OK`
  ```json
  {
    "period": "2026-09",
    "total_amount": 128000,
    "count": 6,
    "items": [
      { "receipt_id": 12, "vendor": "스타벅스 강남점", "amount": 4500 }
    ]
  }
  ```
- 에러: `400 VALIDATION_ERROR`(`period` 형식 오류)

---

### 3.4 Track D — 프론트 연동 대상

Track C backend endpoint는 구현되어 있다. 현재 Track D의 분석·리포트 화면은 이 문서의 endpoint 대신 목데이터를 사용하며, 실제 호출 전환은 별도 frontend 연동 작업으로 관리한다.

---

## 4. 트랙 간 의존 관계

- Track C의 `deductions` 스키마·`GET /reports` 로직은 Track B의 `receipts.amount`/`date` 필드에 의존한다 — **2.2/2.3 스키마를 1일차에 이 문서 기준으로 고정**하고 시작해야 한다.
- Track D는 이 문서의 응답 예시를 그대로 mock JSON으로 써서 1주차부터 화면을 만들 수 있다(백엔드 완성을 기다릴 필요 없음).
- Track A의 `GET /auth/me` 응답 구조는 다른 트랙이 인증 붙일 때 그대로 재사용한다.
