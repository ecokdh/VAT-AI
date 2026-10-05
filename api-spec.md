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

#### 영수증 금액 구분 확장 (2026-10-05, 로컬 구현)

목록·상세 응답과 `PATCH /receipts/{id}/ocr`에 아래 nullable 금액 필드를 추가한다.

| 필드 | 의미 |
|---|---|
| `taxable_supply_amount` | 부가세를 제외한 과세 공급가액 |
| `tax_exempt_amount` | 면세 금액 |
| `vat_amount` | 부가세 |
| `transaction_amount` | 거래 총액 |
| `payment_amount` | 별도로 확인한 결제금액 (총액으로 자동 대입하지 않음) |
| `subtotal_amount` | 주문서의 할인 전 합계 (거래 총액·결제금액과 별도 보관) |

기존 `amount`·`supply_amount`는 보존하며 과세 공급가액으로 일괄 재해석하지 않는다. 기존 레코드의 새 필드는 NULL로 유지된다. 확정 시 `과세 공급가액 + 면세 금액 + 부가세 = 거래 총액`의 정확한 일치를 검사한다. 필요한 값이 누락되거나 합이 다르면 `POST /receipts/{id}/ocr/confirm`이 `409 DATA_CONFLICT`를 반환한다. `money_schema_version=1`인 기존 자료는 원래 값을 보존하며, 미확정 자료는 새 금액 구분을 확인한 뒤 확정해야 한다. 이미 확정된 자료를 일괄 변경하지 않는다. 새 업로드와 금액 구분 입력을 시작한 자료는 버전 2이며, 새 필드를 비워도 옛 금액식으로 확정하지 않는다.

주문서·주문내역의 모호한 `총액`·`합계`는 할인 전 합계로 보관한다. 명시된 거래 총액·할인 후 합계가 없으면 거래 총액은 비워 둔다. 결제금액이나 할인액을 이용한 임의 변환은 하지 않는다.

분해식에서 한 값만 빠지면 나머지 금액으로 계산한다. 명시된 면세 금액이 양수인 거래 총액 전체와 같으면 과세 공급가액·부가세의 누락 값을 0으로 보완한다. 인쇄·입력 값을 덮지 않으며, 총액만으로 1.1을 나누거나 면세 금액을 임의로 0 처리하지 않는다. 음수·비유한 값은 저장을 거절한다. 결제금액과 거래 총액의 일치 여부는 이 분해식의 확정 조건에 포함하지 않는다.

상세 응답의 `money_sources`는 필드별 `kind=printed|manual|calculated`와 계산 시 `rule`을 제공한다. `printed`는 OCR이 영수증 라벨에서 읽었다는 뜻이며 정답 검증을 뜻하지 않는다. 최초 OCR의 원문·직접 추출 값은 `ocr_original`에 보존한다. 계산에 사용한 금액이 수정되면 계산 값을 재계산하고, 직접 수정한 값은 유지한다.

수정 요청은 기존 `base_amount`·`base_supply_amount`·`base_vat_amount`와 새 필드별 `base_taxable_supply_amount`·`base_tax_exempt_amount`·`base_transaction_amount`·`base_payment_amount`·`base_subtotal_amount`에 마지막으로 읽은 값을 보낸다. 저장·확정의 동일 UPDATE에서 읽기 금액을 비교하여 다른 연결에서 바뀐 금액을 덮거나 확정하지 않는다.

#### 누락 단가 보완

`items` 문자열 목록은 유지한다. 상세 응답과 수정 요청의 선택 항목 `item_amounts`는 `item_index`·`quantity`·`line_amount`·`unit_price`를 추가로 보관한다. 응답에는 연결된 `item_name`과 필드별 `sources`도 포함한다. 수량은 유한한 양수, 금액은 유한한 0 이상이어야 한다. 수량·행 금액이 있고 단가만 빠지면 `행 금액 ÷ 수량`으로 보완하며 계산 표시를 제공한다. 직접 입력한 단가는 덮지 않는다. 이미 행 금액에 반영된 할인을 다시 차감하지 않는다.

계산 단가의 수량·행 금액이 수정되면 재계산한다. 계산 입력이 누락된 행은 부분 결과를 유지한다. 단가·수량 누락만으로 OCR 사실 확정을 막지 않는다. 아래 Document AI 계약이 현재 구조화 품목·수정 충돌·반품 처리의 기준이다.

#### Document AI 계약 (2026-10-05, 로컬 구현)

모든 OCR 수정 PATCH와 확정 POST는 필수 양의 정수 `base_revision`을 보낸다. 현재 `revision`과 다르면 `409 DATA_CONFLICT`이며, 화면은 최신 데이터를 재조회한다. 기존 `base_*` 비교 필드는 호환용으로 유지한다. 확정된 증빙의 사실은 OCR PATCH로 변경할 수 없다.

`Receipt` 응답은 `revision`, `transaction_id`, `line_items`, `document`, `evidence_validation`을 추가한다. 구조화 품목의 고정 ID는 이름·순서 변경에도 유지한다. 인쇄 단가와 계산 실효 단가를 구분한다. 응답의 `items`·`item_amounts`는 호환용이다. 구조화 품목과 기존 품목 입력 형식을 동시에 수정하는 요청은 400으로 거절한다. 원본 사진은 인증·소유권 검사를 거친 `GET /receipts/{id}/image`로 조회한다.

OCR 확정 시 별도 `Transaction`에 확인된 사실을 기록한다. `tax_analysis_confirmed=false`이며 세금 공제 확정이 아니다. 여러 증빙을 연결해도 대표 증빙의 금액·품목을 한 번만 집계한다. 거래 응답의 `canonical_receipt_id`·`canonical_line_items`가 집계 대상이며 `receipts`는 대조할 증빙이다. 후속 RAG·Rule Engine에는 로컬 데이터 계약만 제공하며 실제 팀 연동은 별도 단계다.

| 경로 | 동작 / 버전 조건 |
|---|---|
| `GET /transactions`, `GET /transactions/{id}` | 소유 거래 목록·상세 및 확정 사실·증빙 검사 |
| `GET /transactions/{id}/line-items` | 연결 증빙별 품목 목록; 중복 구매로 합산하지 않음 |
| `PATCH /transactions/{id}/line-items/{item_id}` | `base_revision`, `usage`, 선택 `user_note`; 용도 변경 |
| `GET /transactions/{id}/evidence` | 연결된 증빙 |
| `POST /transactions/{id}/evidence/validate` | 증빙별 검사; 공제 판단은 미결정 |
| `POST /transactions/{id}/evidence` | 이미 OCR 확정한 증빙 연결; JSON `receipt_id`, `receipt_revision`, 대상 `base_revision`; 기존 연결 거래가 있으면 `source_transaction_revision` 및 해당 거래의 모든 `source_receipt_revisions` 필요 |
| `GET /reconciliation/issues` | 동일 파일·유사 사진·같은 승인 정보의 중복 후보 |
| `POST /reconciliation/issues/{id}/resolve` | `action=SEPARATE` 또는 `MERGE`; 병합은 `canonical_transaction_id`, 두 `transaction_revisions`, 이동 증빙의 `receipt_revisions` 필요 |
| `POST /transactions/{id}/adjustments` | 원거래 `base_revision`, `adjustment_type`, `supply_date`, 금액·사유로 별도 조정거래 생성 |
| `PATCH /transactions/{id}` | 미해결 조정거래의 `base_revision`, `original_transaction_id`, `original_revision`으로 원거래 연결 |

위 증빙 연결 POST는 기존 증빙을 연결하는 JSON 확장이다. Notion의 파일 업로드 형식 대신 업로드는 기존 `POST /receipts` → OCR 확인·확정 → 연결 순서를 사용한다. 전용 세금계산서·계산서 추출 지원을 의미하지 않는다.

`document.adjustment_type`이 지정된 증빙은 음수 금액을 보존한다. 반품·취소는 총액이 음수이고 금액 구성요소에 양수를 넣을 수 없다. 일반 거래의 음수 입력과 모든 비유한 값은 거절한다. 원거래 없는 조정 증빙은 `UNRESOLVED_ADJUSTMENT`로 남는다. 원거래 연결은 사용자 선택이며 버전·거래처·남은 금액을 검사한다. 중복 후보는 자동 병합·삭제하지 않는다. 병합 전후 증빙과 거래 기록은 보존한다.

`document.date_candidates`는 OCR 원문·후보값·출처를 보존하는 읽기 전용 자료다. PATCH에서 생략하거나 기존 내용과 동일하게 보내는 것은 허용하지만, 후보값·원문·신뢰도·영역을 바꾸거나 후보를 삭제하면 `400 VALIDATION_ERROR`로 요청 전체를 거절한다. 사용자 판단은 `supply_date`, `document_issue_date`, `payment_date` 등 의미가 구분된 날짜 필드에 기록하며 다른 날짜에 자동 복사하지 않는다.

증빙 검사는 가맹점·고객 사업자번호가 있으면 ASCII 숫자 10자리인지 검사한다. 가맹점 번호가 영수증의 `business_number`와 다르면 `CONFLICT` 및 `merchant_business_number_mismatch` 사유를 반환한다. 이 검사는 형식·역할 간 일치 검사이며 외부 사업자 유효성 조회나 공제 판단이 아니다.

금액 KIE는 `신용카드지불`·`현금지불` 같은 명시적 결제 라벨도 읽는다. 카드와 현금에 각각 0이 아닌 금액이 있으면 두 금액이 같아도 전체 결제금액으로 하나를 선택하거나 자동 합산하지 않는다. `payment_amount=null`과 `conflicting_payment_amount_candidates`를 반환해 사진 대조를 요구한다. 좌표가 없는 텍스트·템플릿에서도 서로 다른 금액 후보를 라벨 순서로 선택하지 않는다. 주문서는 일반 `합계`를 할인 전 합계로 유지하며 명시된 `할인후합계`·`거래총액`과 구분한다.

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


### Document AI 값 상태 수정

`PATCH /receipts/{id}/ocr`의 `field_states`는 상호(`vendor`), 거래일(`date`), 사업자번호(`business_number`) 및 기존·분리 금액 필드의 상태를 수정한다. 문서 정보는 `document.sources.<필드>.state`, 구조화 품목은 `line_items[].sources.<필드>.state`로 지정한다.

- `READ`: 읽은 값이 있어야 한다.
- `UNREVIEWED`: 빈 값 또는 아직 확인하지 않은 후보값을 보존한다.
- `ABSENT / FAILED / NOT_APPLICABLE`: 해당 값은 빈 값이어야 한다. 화면에서 상태를 선택하면 입력칸을 비운다.
- 수동 수정은 이전 글자 영역을 보존하고 OCR 신뢰도를 제거한다. 클라이언트가 보낸 `kind`, 글자 영역, 신뢰도를 새로운 OCR 근거로 신뢰하지 않는다.
- 명시적으로 미기재·판독 실패·해당 없음으로 지정한 누락 금액은 계산으로 다시 채우지 않는다. 계산 결과가 필요한 경우 값을 확인해 입력하거나 미확인 상태로 되돌려 저장한다.
- 상호·거래일·과세 공급가액·면세금액·VAT·거래 총액이 명시적으로 미확인 상태이면 OCR 확정을 409로 거절한다. 선택 정보의 누락만으로 세무 판정을 내리지 않는다.
- 상태 수정도 `base_revision`이 필요하며, 변경된 상태는 재조회 응답의 `money_sources` 또는 `document.sources`에 포함된다.
- 증빙 검사의 필수정보는 후보값이 있어도 명시적으로 `UNREVIEWED`이면 충족되지 않는다. 검사 결과는 `INCOMPLETE`와 해당 `missing_fields`·`unreviewed_fields`를 반환한다. 카드·현금영수증 승인번호, 세금계산서·계산서의 발행일과 사용자 사업자번호에도 같은 규칙을 적용한다. 미확인 상태가 없는 기존 기록은 기존 값으로 검사한다.


### 조정거래에 확정 증빙 연결

`POST /transactions/{id}/evidence`는 원거래가 연결된 `NEEDS_EVIDENCE / NEEDS_CONTEXT` 조정거래에도 사용할 수 있다. `base_revision`, 선택 증빙의 `receipt_revision`, 원래 증빙 거래의 `source_transaction_revision`, 원거래의 `original_revision`을 요구한다. 원래 증빙 거래에 다른 증빙이 있으면 각각의 현재 버전을 `source_receipt_revisions`로 보낸다.

같은 조정 종류·총액·금액 분해를 확인하고, 원거래의 거래처 및 조정일과 증빙을 대조한다. 다른 원거래에 연결된 증빙은 거절한다. 하나의 변경 작업으로 증빙을 이동하고 원래 증빙 거래를 `MERGED`로 남긴다. 모든 증빙·음수 금액·원거래 연결을 보존하며, 조정거래는 `NEEDS_CONTEXT`, `ocr_confirmed=true`, `tax_analysis_confirmed=false`가 된다. 불일치나 버전 충돌은 409이며 거래·증빙·원거래 버전 변경도 롤백한다.

조정 금액의 누적 및 원거래 잔액 검사에서는 `MERGED` 기록을 제외한다. 이미 연결된 증빙을 현재 버전으로 다시 요청하면 추가 집계나 버전 변경 없이 현재 결과를 반환한다.

### 원거래 병합과 연결된 조정거래

일반 거래를 병합할 때 원래 거래의 활성 반품·취소·조정거래도 대표 원거래로 연결을 옮긴다. 음수 금액, 조정 사실 및 조정 증빙은 보존한다. 중복 해결 요청의 `transaction_revisions`에는 양쪽 원거래와 연결된 활성 조정거래의 버전을 포함한다. 일반 거래의 증빙 연결 요청에서는 연결된 조정거래 버전을 `related_transaction_revisions`로 보낸다.

관련 버전 누락·충돌, 증빙 버전 충돌, 병합 후 누적 조정액의 원거래 금액 초과는 409로 거절하며 모든 거래·증빙 버전과 연결 변경을 롤백한다. 거래 화면은 대표 원거래에 연결된 조정거래를 별도 목록으로 표시한다.

### 기존 확정 기록의 거래 전환

`20261005a4` 마이그레이션은 `confirmed=true`이고 거래가 연결되지 않은 기존 영수증만 거래로 연결한다. 기존 확정 여부·영수증 revision·원본 금액·품목은 변경하지 않으며, 이미 연결된 거래와 미확정 영수증은 그대로 유지한다. 거래의 `facts.legacy_confirmation`은 전환 경로와 기존 금액 스키마 버전을 기록한다.

거래 총액은 저장된 `transaction_amount`를 우선하고 없으면 기존 `amount`를 사용한다. 기존 `supply_amount`는 같은 이름으로 보존하며 과세 공급가액·면세금액으로 재분류하지 않는다. 기존 확정 기록을 세무분석 확정으로 취급하지 않고 부족한 금액 분해·문서 정보는 현재 증빙 검사에 표시한다. 명시적 조정 문서 또는 음수 총액은 원거래가 없는 `UNRESOLVED_ADJUSTMENT`로 남기며 반품·취소 종류를 임의로 추정하지 않는다.

이 데이터 전환의 downgrade는 기존 스키마와 호환되는 연결·거래를 보존한다. 다시 upgrade해도 이미 연결된 증빙에 거래를 추가 생성하지 않는다.

### 수정 후 중복 후보 갱신

기존 파일의 해시가 없는 경우 로컬 유지보수 함수 `backfill_image_fingerprints(session, storage)`로 누락된 SHA-256·pHash를 채울 수 있다. 호출자가 트랜잭션을 커밋하며 원본 사진·금액·품목·확정 여부·revision은 변경하지 않는다. 파일을 읽을 수 없거나 이미 저장된 SHA-256과 파일 내용이 다르면 건너뛰고 사유를 반환한다. 중복 후보만 갱신하며 자동 병합하지 않는다. 외부 OCR 호출은 없다.

거래일시 `document.transaction_datetime`은 날짜와 시각을 함께 포함한 ISO 형식으로 저장한다. 잘못된 날짜·시각이나 날짜만 보낸 값은 422로 거절한다. 명시된 시간대는 보존하며 시간대가 없는 값에 임의 시간대를 붙이지 않는다. 공급일·발행일·결제일은 각각 별도 필드다.

실효 단가는 행 금액을 수량으로 나눈 계산값이다. 숫자로 표현할 수 없는 계산 결과는 `FAILED`로 남기고 원래 수량·행 금액·인쇄 단가는 보존한다. 계산 출처에는 수량과 행 금액의 글자 영역을 연결하며 OCR 인식 신뢰도를 계산 신뢰도로 재사용하지 않는다.

영수증 수정과 중복 후보 대조를 같은 DB 변경 작업으로 저장한다. 파일 해시·pHash·승인번호/거래일시/가맹점 사업자번호/거래총액을 다시 대조해 후보의 `active`를 갱신한다. 현재 일치하지 않는 후보는 `active=false`로 보존하고 화면의 미해결 후보 목록에서 제외한다. 다시 일치하면 같은 후보 ID를 활성화한다.

`resolved`·`action`은 사용자의 결정이며 자동 갱신으로 되돌리지 않는다. 비활성 후보에 대한 해결 요청은 409로 거절한다. DB의 영수증 쌍 유일 제약과 충돌 처리로 같은 쌍의 후보를 중복 생성하지 않는다. 후보 갱신 실패는 영수증 수정도 롤백한다.
