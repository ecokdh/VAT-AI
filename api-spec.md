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
  {
    "email": "owner@shop.com",
    "password": "plain-text-pw",
    "name": "김대표",
    "business_name": "가게 이름",
    "business_number": "1234567890",
    "terms_accepted": true,
    "privacy_accepted": true,
    "marketing_accepted": false
  }
  ```
- 필수 약관 또는 개인정보 동의가 `false`이면 `400 CONSENT_REQUIRED`를 반환하고 가입하지 않습니다.
- 서비스 이용약관, 개인정보 처리방침, 마케팅 안내 선택을 각각 `consent_records`에 선택 여부와 서버 UTC 시각으로 기록합니다. 기존 계정의 동의 기록은 추정해 생성하지 않습니다.
- Response `201 Created`
  ```json
  {
    "access_token": "eyJ...",
    "user": { "id": "uuid", "email": "owner@shop.com", "name": "김대표", "created_at": "2026-09-16T09:00:00Z" }
  }
  ```
- 에러: `409 EMAIL_ALREADY_EXISTS`, `400 VALIDATION_ERROR`

#### `POST /auth/email-availability`
- 인증: 불필요
- Request body: `{ "email": "owner@shop.com" }`
- Response `200 OK`: `{ "available": true }` 또는 `{ "available": false }`
- 형식이 유효하지 않은 이메일은 `400 VALIDATION_ERROR`를 반환합니다. 최종 가입 시에도 중복을 다시 검사합니다.

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

---

## 5. VAT-AI v2 거래·분석 계약

기존 v1 경로와 응답은 유지한다. 새 거래 작업은 `/v2` 아래에 별도 계약으로 추가한다.

### 5.1 확정 거래 및 휴지통

- `POST /v2/transactions`: 사용자가 검토한 거래를 초안으로 생성한다.
- `POST /v2/transactions/from-receipt/{receipt_id}`: 소유자와 OCR 완료 상태를 확인한 뒤 초안을 생성한다. OCR 결과를 자동으로 확정하지 않는다.
- `PATCH /v2/transactions/{id}`: 거래 필드를 수정하고 revision을 올린다. 매입 분석 결과는 `stale`이 되어 예상 공제액에서 즉시 제외한다.
- `POST /v2/transactions/{id}/confirm`: 검토가 끝난 거래를 확정한다.
- `DELETE /v2/transactions/{id}`: 휴지통으로 이동한다. 예상 세액 집계에서 즉시 제외한다.
- `GET /v2/trash`, `POST /v2/trash/{id}/restore`: 휴지통 조회와 복원을 제공한다. 복원한 매입은 재분석 전까지 예상 공제액에서 제외한다.
- `POST /v2/trash/{id}/permanent-delete-request`: 법정 보존 여부 검토 요청을 기록한다. 자동 영구 삭제는 하지 않는다.

### 5.2 선택 분석 및 예상 세액

- `POST /v2/analysis-runs`는 선택한 확정 매입 거래의 ID와 revision을 작업에 고정하고 `202 Accepted`와 `PENDING`을 반환한다.
- `GET /v2/analysis-runs/{id}`로 `PENDING → PROCESSING → COMPLETED / FAILED` 상태를 조회한다. 실패는 최대 3회까지 재시도한다.
- 분석 결과는 작업을 시작할 때 고정한 revision과 현재 revision이 같을 때만 저장한다. 수정되거나 휴지통으로 이동한 거래는 `SKIPPED_STALE` 처리한다.
- 아직 법령 근거 인덱스가 설정되지 않은 상태에서는 공제액을 추정하지 않고 `CAUTION`으로 보류한다.
- 분석 모델은 `app.analysis.contract.PurchaseAnalyzer`의 `analyze(request)` 어댑터로 연결한다. 서버 설정 `DEDUCTION_ANALYZER=모듈경로:팩토리함수`로 구현체를 선택하며, 비워 두면 안전 기본 구현이 모든 판단을 검토 보류한다. 입력에는 확정 거래 사실, 연결된 영수증 OCR 원문(최대 40,000자), 확인된 사업자 컨텍스트가 포함되며 사용자 비밀 정보는 포함하지 않는다.
- 모델 어댑터 입력은 `AnalysisRequest` 계약 버전 `v1`이며 확정 거래 사실과 확인된 사업자 컨텍스트를 받는다. 출력은 `DEDUCTIBLE`, `NOT_DEDUCTIBLE`, `NEEDS_REVIEW`, `INSUFFICIENT_INFO` 중 하나와 설명·부족 정보·근거 출처·모델/지식 버전이다. 최종 분류에 근거 출처가 없으면 `NEEDS_REVIEW`로 낮춘다.
- 모델 출력 스키마에는 금액 필드가 없다. 어댑터가 금액을 반환하면 검증 실패로 작업을 재시도하며, 세액 산술은 계속 `app/tax_engine`에서만 수행한다. `NOT_DEDUCTIBLE`은 집계에서 제외하고, `INSUFFICIENT_INFO`는 미계산, `NEEDS_REVIEW`는 CAUTION으로 집계한다.
- 동료 모델은 이 계약을 구현하는 별도 Python 어댑터로 연결할 수 있다. 모델 제공자·프롬프트·추론 로직을 거래 API 및 세액 엔진과 분리해 교체 가능하게 둔다.
- `GET /v2/tax-estimates/2026?period=...`는 일반과세자 `2026-H1`, `2026-H2`, 간이과세자 `2026-YEAR`만 허용한다. 과세유형과 기간은 확인된 사업자 프로필에서 읽는다.
- 세액 산술은 `app/tax_engine`의 결정적 규칙으로만 계산한다. 과세기간·업종 또는 거래 사실이 불충분하면 `PARTIAL` 또는 `UNAVAILABLE`을 반환한다.
- `GET/PUT /v2/business/tax-profile`은 2026년 매출, 사업자 형태·업종, 개·폐업 및 휴업 기간, 과세유형 변경 정보를 조회·저장한다. 초안은 계산 근거로 쓰지 않으며, 사용자가 확인 완료한 정보만 세율·공제 한도 판단에 반영한다.

### 5.3 교체 가능한 매입 분석 모델

- 구현 계약은 `app.analysis.contract.PurchaseAnalyzer`의 `analyze(AnalysisRequest) -> AnalysisDecision`이다. `DEDUCTION_ANALYZER=모듈경로:팩토리함수`로 주입하며, 미설정이면 안전 기본 구현이 `NEEDS_REVIEW`를 반환한다.
- 입력 계약 `v1`은 거래 사실, 연결된 OCR 원문(최대 40,000자), 확인된 사업자 컨텍스트를 제공한다. 로그인 정보나 비밀키는 모델로 전달하지 않는다.
- 출력은 `DEDUCTIBLE`, `NOT_DEDUCTIBLE`, `NEEDS_REVIEW`, `INSUFFICIENT_INFO` 중 하나, 근거·설명·누락정보 및 모델/지식 버전이다. 확정 판정에 법적 근거가 없으면 `NEEDS_REVIEW` 처리한다.
- 모델은 세액 또는 공제액 숫자를 반환하지 않는다. 금액 산술은 결정적 Tax Rule Engine에서만 수행한다.

### 5.4 교체 가능한 OCR 파이프라인 및 진행 상태

- `app.ocr_pipeline.contract.OcrPipeline.process(OcrPipelineInput, report_progress)`가 OCR 어댑터 계약이다. `OCR_PIPELINE=모듈경로:팩토리함수`로 교체하며, 미설정이면 CLOVA 호환 어댑터를 사용한다.
- 공통 단계는 사진 품질 확인 → 증빙 글자 인식 → 거래 정보·금액 구분 → 누락·오독 항목 확인이다. 단계별 상태와 진행률은 DB에 기록한다.
- `GET /v2/receipts/{receipt_id}`는 기존 v1 응답을 바꾸지 않고 v2에서 단계별 상태, 경고, 누락 필드, 추출 확인 여부, 사용자 재시도 횟수, 파이프라인 이름/버전을 추가 제공한다.
- 일부 필드만 인식된 작업은 `PARTIAL` 결과와 누락 필드를 반환하고 영수증 상태를 완료로 둔다. 사용자는 추출 결과 화면에서 보완한 뒤 저장·확정한다. 파이프라인 실행 자체가 실패한 경우에는 작업 재시도 후 최종 실패를 기록한다.
- OCR 결과는 자동 확정 거래가 아니며 분석·세액 합계에 자동 반영되지 않는다.
- 사용자 흐름은 `업로드 → OCR 진행 → 추출 결과 확인·누락 필드 보완 → 확인 후 매입 보관함 → 거래 정보 확인·저장 → 메인 화면`이다. 추출 결과 확인과 거래 확정은 별도 단계이며 거래 확정 직후 분석을 자동 실행하지 않는다.
- `POST /v2/receipts/{receipt_id}/confirm-extraction`은 거래처·금액·거래일을 확인해 OCR 추출값으로 저장하고 보관함 진입을 허용한다. 필수 추출 필드가 없으면 사용자가 이 화면에서 입력한다.
- `GET /v2/receipt-inbox`는 추출 확인을 마친 OCR 결과 중 아직 거래로 전환되지 않은 항목만 반환한다. 거래 확정 시 영수증 연결 거래를 저장하고 `/dashboard`로 이동한다.
- OCR 작업이 실패하면 `POST /v2/receipts/{receipt_id}/retry`로 같은 사진을 한 번 재시도할 수 있다. 실패 안내 화면에서 새 사진 촬영이나 보관함 이동도 선택할 수 있다.
- 영구 삭제 검토 요청은 `retention_status=not_required`인 거래에서만 기록한다. `required`와 `under_review`는 각각 보존 기간 중, 보존 여부 미확인으로 차단한다. OCR 어댑터의 보존 상태 분류는 기본적으로 `under_review`이며, 법령상 보존 상태를 분류할 근거를 어댑터 계약에서 제공해야 한다.
- 일반과세자의 의제매입세액은 거래의 대상 품목·과세사업 사용·증빙 유형을 확인하고, 사업자 형태·업종·관련 과세 매출에 따른 규칙을 적용할 수 있을 때만 계산한다. 간이과세자에는 의제매입세액공제를 적용하지 않는다. 불명확한 사례는 계산 보류 대상이다.
- 의제매입 한도용 관련 과세 매출은 전체 과세 매출과 별도 필드로 확인한다. 관련 매출이 입력되지 않은 거래는 계산에서 제외하며, 제조업 일반과세자의 2026년 2기 의제매입은 연간 합산 조정 요건을 확인할 때까지 보류한다.

### 5.3 현재 구현 경계

위 계약과 작업 저장소는 v2 구현 기준이다. v1 영수증 OCR은 기존 동기 경로를 유지하고, `POST /v2/receipt-jobs`는 OCR 작업을 비동기로 접수한다. `POST /v2/pdf-jobs?period=...`는 검토 보류·미계산 거래가 있어도 현재 예상치와 주의사항을 담아 PDF 작업을 생성하며, `GET /v2/jobs/{id}`로 작업 상태를 조회한다. 완료된 PDF는 `GET /v2/pdf-jobs/{id}/download`로 소유자만 내려받을 수 있다. 워커는 별도 프로세스로 실행한다. 운영 PDF 생성에는 `pdfkit`, `wkhtmltopdf` 실행 파일 및 한글 글꼴 설정이 필요하고, `S3_BUCKET` 설정 시 업로드 파일과 PDF를 S3에 저장한다. 저장소 설정이 없으면 로컬 파일 저장소를 사용한다.
