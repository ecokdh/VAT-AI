# Document AI 스프린트 코드 상세 해설

2026-10-05 Document AI 구현 설명. 최신 main의 사업자 검증·개발환경을 통합한 일반 PR 공유용 문서다. 앱 의존성 파일은 변경하지 않았다. 정답·사진·캐시는 로컬에 보존하며 저장소에 포함하지 않았다.

## 1. 이번 스프린트의 실제 목적

사진에서 글자를 읽는 것만으로는 영수증 서비스를 만들 수 없다. 글자 `1,000`을 읽었더라도 그 숫자가 수량, 단가, VAT, 할인, 결제금액 중 무엇인지 알아야 한다. 같은 영수증을 다시 찍은 사진은 새 구매로 더하면 안 되고, 반품 영수증의 음수 금액은 없애면 안 된다. 사용자가 확인한 뒤 확정하는 순간에 다른 화면이 금액을 수정해도 이전 금액을 확정해서는 안 된다.

이번 코드는 이 문제를 다음 흐름으로 처리한다.

```text
사진 업로드
 → 파일 형식·크기·실제 이미지 검사
 → 현재 앱의 간단한 품질 검사
 → OCR 응답 수신
 → 글자·좌표·신뢰도를 내부 형식으로 변환
 → KIE로 품목 행과 금액 역할 구분
 → 읽은 값 / 계산한 값 / 사용자 수정값을 구분해 저장
 → 원본 사진과 값을 대조하고 수정
 → 수정 버전과 금액 관계를 검사해 OCR 확정
 → 거래 생성 또는 다른 증빙과 연결
 → 중복 후보와 반품·취소 원거래 연결
```

별도로 저장된 OCR 응답을 평가하는 프로그램과 품질분류 실험 프로그램이 있다. 이 둘은 사용자가 영수증을 올릴 때 실행되는 앱 처리와 분리되어 있다. Tax Rule Engine, 공제 판단, PDF, 팀의 실제 RAG 연결은 이번 구현 범위 밖이다.

## 2. 코드를 읽기 위한 기본 개념

### 2.1 요청, 응답, DB 모델은 서로 다른 역할이다

`models.py`의 SQLModel 클래스는 DB에 어떻게 저장할지 정한다. `schemas.py`와 `document.py`의 Pydantic 모델은 API 입력·출력이 어떤 구조여야 하는지 검사한다. `router.py`는 URL을 함수에 연결하고, `service.py`는 실제 순서와 저장 규칙을 수행한다.

예를 들어 `Receipt.document_json`은 DB의 문자열 열이다. API에서는 이것을 JSON 문자열 그대로 보여주는 대신 `DocumentFacts` 객체로 읽어 `document` 필드에 반환한다. DB 저장 모양과 화면에 전달하는 모양이 같을 필요는 없다.

`Field(default_factory=list)`는 객체마다 새 목록을 만든다. 여러 영수증이 같은 기본 목록을 공유하는 문제를 피한다. `FiniteFloat`는 NaN·무한대를 배제한다. `Literal`은 정해진 값만 허용한다. `extra="forbid"`는 정해지지 않은 입력 필드를 거절한다. 단, 모든 모델과 모든 자유형 JSON에 이 설정이 일괄 적용되는 것은 아니다.

### 2.2 None, 0, 누락된 요청 필드는 다르다

`None`은 값이 없다는 뜻이고 `0`은 확인된 숫자 0이다. PATCH에 필드가 아예 없는 것은 그 필드를 수정하지 않는다는 뜻이다. PATCH에 `null`을 명시하면 비우겠다는 의도가 될 수 있다.

`payload.model_dump(exclude_unset=True)`가 중요한 이유가 이것이다. 요청에서 보내지 않은 기본값까지 덤프해서 기존 데이터를 모두 비우지 않도록 한다. 이후 서비스가 명시적 값 상태와 계산 규칙을 함께 검사한다.

### 2.3 session, flush, commit, rollback

`session.add()`는 변경할 대상을 세션에 등록한다. `flush()`는 SQL을 DB에 보내 ID와 제약 등을 확인하지만 최종 확정은 하지 않는다. `commit()`은 묶여 있는 DB 작업을 확정하고, `rollback()`은 아직 확정되지 않은 DB 작업을 되돌린다.

파일 저장은 DB 트랜잭션에 포함되지 않는다. 따라서 DB 실패 시 파일을 지울지 보존할지 별도의 판단이 필요하다. 이 차이는 업로드 실패 처리에서 다시 설명한다.

### 2.4 async와 일반 함수

OCR 네트워크 요청은 `async`와 `await`를 사용한다. 외부 서버 응답을 기다리는 작업이다. 금액 계산, 좌표 해석, DB 조건 검사 자체는 일반 함수다. `async`라는 표시가 병렬 계산이나 머신러닝을 의미하지는 않는다.

## 3. 파일 지도와 읽기 순서

| 파일 | 알아야 하는 핵심 |
|---|---|
| `app/receipts/models.py` | 영수증·거래·품목·중복 후보 저장 구조 |
| `app/receipts/document.py` | 품목·증빙·출처 계약, 할인 검증, 증빙 검사 |
| `app/receipts/schemas.py` | API 입력·출력, revision 필수, 호환 응답 |
| `app/receipts/money.py` | 과세·면세·VAT 계산과 합계 검증 |
| `app/receipts/ocr_client.py` | CLOVA 응답 통합, 부분 결과, Windows OCR fallback |
| `app/receipts/kie.py` | 좌표를 이용한 금액·품목 구조화 |
| `app/receipts/metadata.py` | 문서 종류·날짜·승인번호·사업자 역할 후보 |
| `app/receipts/service.py` | 업로드·수정·확정 전체 처리 |
| `app/receipts/storage.py` | 인증 조회에 쓰는 로컬 원본 파일 저장 |
| `app/receipts/quality.py` | 앱에서 실제 사용하는 간단한 품질 규칙 |
| `app/receipts/fingerprints.py` | SHA-256, pHash, 기존 사진 해시 보완 |
| `app/receipts/transactions.py` | 거래 연결·중복 검토·반품 한도 |
| `app/receipts/evaluation.py` | 저장 응답에 대한 동일 조건 비교평가 |
| `app/receipts/quality_experiment.py` | CNN·MobileNet 로컬 비교 실험 |
| `frontend/src/pages/receipts/OcrResultEditPage.tsx` | 사진 대조 화면의 전체 상태와 저장·확정 |
| `frontend/src/components/ReceiptReview.tsx` | 원본 사진, 좌표 표시, 품목 행 편집 |
| `frontend/src/components/DiscountEditor.tsx` | 할인 범위와 중복 포함 관계 입력 |
| `frontend/src/pages/transactions/TransactionPage.tsx` | 증빙 연결과 중복·반품 검토 화면 |
| `frontend/src/pages/storage/PurchaseStoragePage.tsx` | 대표 증빙만 합산하는 보관함 |
| `app/migrations/versions/20261005_*.py` | 기존 데이터 보존하며 새 구조 추가 |
| `tests/test_document_ai.py`, `test_receipts.py`, `test_transactions.py`, `test_migrations.py` | 계약·경합·연결·보존에 대한 실행 가능한 예시 |

처음에는 4~8장을 읽고, 이어서 업로드·KIE·수정·확정 순서로 읽는 것이 좋다. 마지막 부록에는 현재 코드에서 뽑은 실제 함수와 클래스 위치가 있다.

## 4. Receipt, Transaction, LineItem을 왜 나눴나

### 4.1 Receipt: 증빙 한 장

`Receipt`에는 소유 사용자, 원본 사진 저장 키, OCR 원문, 처음 판독한 스냅샷, 현재 수정값, 금액, 문서 정보, 확정 여부, revision, 해시, 연결된 거래 ID가 있다.

사진을 두 번 올리면 Receipt는 두 개일 수 있다. 이것만으로 구매가 두 번 발생했다고 볼 수는 없다. `image_url`이라는 이름은 남아 있지만 실제 로컬 구현에서는 외부 공개 URL이 아니라 상대 저장 키다.

`ocr_raw`는 읽은 텍스트, `ocr_original`은 최초 정규화 결과의 스냅샷, `ocr_response_json`은 제공자 응답이다. 셋은 목적이 다르다. 최초 스냅샷이 보존되어야 사용자가 고친 뒤에도 원래 판독 결과를 대조할 수 있다.

### 4.2 Transaction: 실제 경제적 사건

`Transaction`에는 사용자, 거래 사실 JSON, revision, 업무 상태, 원거래 ID, 조정 종류가 있다. 여러 Receipt의 `transaction_id`가 같은 Transaction을 가리킬 수 있다.

11,000원 구매의 카드전표와 일반 영수증을 연결해도 거래 총액은 11,000원이다. 22,000원으로 합산하지 않는다. 대표 증빙은 `facts.source_receipt_id`로 식별하고 대표 품목은 그 증빙에서 제공한다.

### 4.3 LineItem: 이름과 순서가 바뀌어도 같은 품목

`LineItem` 테이블은 ID, receipt_id, position, data_json을 가진다. 이름은 JSON 안의 값이고 순서는 position이다. 둘 다 ID와 분리된다.

```text
처음: id=A, position=0, name="우유"
수정: id=A, position=1, name="저지방 우유"
```

여전히 같은 품목 A다. 할인 참조가 이름이나 배열 번호를 따라가면 이름 수정·재정렬 때 다른 품목에 붙을 수 있으므로 고정 ID를 사용한다.

### 4.4 ReconciliationIssue: 중복 의심과 사용자 결정

이 테이블은 두 영수증의 후보 관계를 저장한다. `reason`은 후보 이유, `active`는 지금도 조건이 맞는지, `resolved`는 사용자가 결정했는지, `action`은 MERGE 또는 SEPARATE이다.

OCR 수정으로 승인번호가 달라져 후보 조건이 사라져도 과거 사용자 결정을 지워서는 안 된다. 현재 일치 여부와 결정 이력을 별도 열로 나눈 이유다.

## 5. 품목 데이터 계약: StructuredItem

| 필드 | 뜻과 주의점 |
|---|---|
| `id` | 서버가 저장한 고정 ID. 새 품목은 처음에는 null 가능 |
| `name` | 현재 사람이 읽기 좋은 이름. 빈 이름 불가 |
| `original_name` | 처음 확보한 원문 이름. 이름 수정 때 기존 원문 유지 |
| `specification`, `unit` | 규격과 단위. 저장·편집 가능하지만 자동 추출 완료를 뜻하지 않음 |
| `quantity` | 소수·음수 가능. 중량 판매와 반품을 보존. 미기재는 null |
| `printed_unit_price` | 종이에 실제 인쇄된 단가. 음수 불가 |
| `effective_unit_price` | 행 금액 ÷ 수량으로 계산한 실효 단가 |
| `line_amount` | 해당 행 금액. 반품 부호 보존 |
| `discount_amount` | 품목 할인 기록. 음수 불가 |
| `tax_type` | UNKNOWN/TAXABLE/EXEMPT/ZERO_RATED. 세무 공제 판단 아님 |
| `usage` | UNKNOWN/BUSINESS/PERSONAL/MIXED. 사용자 용도 입력 |
| `user_note` | 사용자 메모 |
| `sources` | 필드마다 출처·상태·좌표·인식 신뢰도 |

`complete_item()`은 기존 실효 단가를 초기화하고 현재 수량·행 금액으로 다시 계산한다. 수량이 null 또는 0이면 나누지 않는다. 무한대나 float로 표현할 수 없는 극단적 값도 검토 가능한 부분 결과로 남긴다.

예를 들어 인쇄 단가가 2,000원, 수량이 2개, 할인 적용 행 금액이 3,000원이면 인쇄 단가는 2,000원, 실효 단가는 1,500원이다. 계산했다고 인쇄 단가를 1,500원으로 바꾸면 원문 사실을 손상한다.

계산값 출처에는 수량과 행 금액의 글자 영역을 합쳐 보존한다. 계산값에는 OCR 신뢰도 숫자를 새로 붙이지 않는다. OCR 95%는 나눗셈 결과가 95% 확률로 올바르다는 뜻이 아니기 때문이다.

## 6. 값의 출처와 상태: Evidence

출처 `kind`는 `ocr`, `manual`, `calculated`다. 금액의 기존 호환 계약은 OCR 인쇄값을 `printed`라고 표현하므로 두 명칭이 코드에 공존한다. 모든 출처 문자열이 하나의 enum으로 통일된 상태는 아니다.

상태는 다섯 가지다.

| 상태 | 실제 의미 | 예시 |
|---|---|---|
| READ | 값이 읽히거나 확인됨 | 총액 11,000원 |
| ABSENT | 사진에 실제로 기재되지 않음 | 수량 칸 자체 없음 |
| FAILED | 기재된 것으로 보이지만 판독 실패 | 수량이 `1?`로 흐림 |
| UNREVIEWED | 후보 또는 빈 값의 의미를 아직 확인 안 함 | 금액 후보 두 개 충돌 |
| NOT_APPLICABLE | 이 문서·필드에 해당 없음 | 카드가 아닌 증빙의 카드정보 |

`None`만 저장하면 ABSENT와 FAILED를 구분할 수 없다. 그래서 값과 상태를 함께 저장한다. READ인데 값이 없거나 ABSENT인데 값이 남아 있는 모순은 수정 저장에서 검사한다.

사용자가 수정하면 kind는 manual, confidence는 null로 바뀐다. 원래 글자 영역은 대조용으로 남을 수 있지만 수정한 값이 그 영역에 실제로 인쇄되어 있다는 보증은 아니다. 클라이언트가 confidence를 1.0으로 보내도 서버가 그대로 신뢰도를 승격하지 않는다.

## 7. 금액 계약과 계산 규칙

### 7.1 여섯 금액의 역할

```text
taxable_supply_amount = 과세 공급가액, VAT 제외
tax_exempt_amount     = 면세 거래금액
vat_amount            = 부가세
transaction_amount    = 거래 총액
payment_amount        = 결제금액
subtotal_amount       = 할인 전 합계
```

기본 등식은 `과세 공급가액 + 면세금액 + VAT = 거래 총액`이다. 결제금액과 할인 전 합계는 이 등식의 대체값으로 자동 사용하지 않는다. 상품권·포인트·복합 결제·주문서 등에서는 서로 다를 수 있기 때문이다.

기존 `amount`, `supply_amount`는 호환용으로 보존한다. 신규 분리 금액 계약은 `money_schema_version=2`로 표시한다. 기존 열이 있다고 새 과세 금액으로 일괄 재해석하지 않는다.

### 7.2 complete_money가 실제로 하는 일

입력 사전을 복사하고, 기존 값은 덮지 않는다. 누락된 한 항목을 수학적으로 유일하게 결정할 수 있을 때만 계산한다.

```text
거래 총액 11,000 / 면세 0 / VAT 1,000 / 과세 공급가액 없음
 → 과세 공급가액 = 11,000 - 0 - 1,000 = 10,000

과세 10,000 / 면세 3,000 / VAT 1,000 / 거래 총액 없음
 → 거래 총액 = 14,000

거래 총액 5,000 / 면세 5,000 / 다른 금액 없음
 → 확인된 전액 면세 관계에서 과세 0, VAT 0을 보완

거래 총액 11,000만 있음
 → 과세·면세·VAT가 여러 방식으로 가능하므로 추정하지 않음
```

ABSENT/FAILED/NOT_APPLICABLE로 명시된 값은 자동 계산으로 다시 채우지 않는다. 사용자의 상태 결정을 계산 규칙이 덮지 않도록 한다. UNREVIEWED와 명시적 실제 미기재는 다른 취급이다.

`Decimal(str(value))`로 계산·합계 검사를 수행한다. DB 자체는 Float 열을 사용하므로 전체 시스템이 Decimal 저장으로 바뀐 것은 아니다. 금액 일치 검사는 현재 오차 허용 없이 정확한 합을 요구한다.

### 7.3 money_problem의 역할

네 필수 금액이 필요한 상황에서 값이 비면 누락 문제를 반환한다. 값이 있으면 과세+면세+VAT와 거래총액이 같은지 검사한다. 다르면 충돌 문제다.

품목 행 총합과 모든 할인·쿠폰을 자동 회계적으로 완전 대사하는 엔진은 아니다. 현재 구현된 핵심 대사는 위 금액 분해 등식이다. 품목 합계·공동 할인 배분·결제수단 합산을 모두 지원한다고 말하면 범위를 넘는다.

## 8. 할인·쿠폰 계약

`Discount`는 ID, 종류, 적용 범위, 금액, 품목 ID 목록, 행 금액 반영 여부, 다른 할인에 포함된 ID를 가진다.

ITEM은 품목 하나, GROUP은 품목 그룹, TRANSACTION은 전체 거래다. ITEM에는 정확히 한 품목 ID가 필요하고 GROUP은 비어 있으면 안 된다. TRANSACTION에 품목 목록을 붙이면 모순이다.

할인 ID 중복, 품목 참조 중복, 존재하지 않는 할인 포함 관계, 포함 관계의 순환을 검사한다. 저장 서비스는 참조한 품목 ID가 실제 그 영수증에 속하는지도 확인한다.

```text
행 금액 3,000원에 할인 1,000원이 이미 반영됨
 → 할인 기록은 남기되 행 금액에서 다시 1,000원을 빼지 않음

전체 할인 2,000원 안에 쿠폰 500원이 포함됨
 → 쿠폰을 별도 추가 할인으로 중복 차감하지 않도록 포함 관계 기록
```

현재 기능은 할인 의미를 구조적으로 보존하고 사용자 입력을 검증한다. 모든 영수증의 쿠폰을 자동 추출·배분해 완전한 할인 계산을 끝내는 기능은 아니다. 공동 쿠폰을 품목마다 임의 분배하지 않는다.

## 9. 업로드: router → service → storage → OCR

### 9.1 API 입구

POST `/receipts`는 multipart의 `file`을 받고, 인증된 사용자와 DB 세션을 주입받는다. 읽을 때 최대 업로드 크기보다 한 바이트 더 읽어 제한 초과를 검사할 수 있다. 성공은 201이다.

소유 사용자 ID는 요청 JSON에서 마음대로 선택하는 값이 아니라 로그인 정보에서 가져온다. 상세 조회·사진 조회·수정도 ID와 사용자 조건을 함께 검사한다.

### 9.2 실제 이미지 검증

확장자만 믿지 않는다. JPEG/PNG의 시작 바이트로 형식을 찾고 Content-Type과 비교한다. 빈 파일, 제한 초과, 지원하지 않는 형식, 잘못된 이미지, 과도한 픽셀 수를 거절한다. PIL `verify()` 후 다시 열어 `load()`하는 이유는 검증과 실제 디코딩을 구분해서 확인하기 위해서다.

이 검사는 파일이 이미지라는 검사다. 영수증 내용이 모두 보인다는 검사나 세무상 유효하다는 검사가 아니다.

### 9.3 파일 저장

`LocalFileStorage.save()`는 사용자별 디렉터리에 UUID 이름으로 저장한다. 원래 파일명에 기대어 경로를 만들지 않는다. `xb`는 기존 이름을 덮어쓰지 않는 바이너리 생성 방식이다.

read/delete는 경로를 절대 경로로 해석한 뒤 저장 루트 안에 있는지 확인한다. `../`로 다른 파일을 읽는 경로 이탈을 막는다. Storage Protocol은 다른 저장소로 바꿀 경계를 제공하지만 이번에 S3 저장소를 구현한 것은 아니다.

### 9.4 품질 불량은 OCR 호출 전에 retake

품질 규칙이 거절하면 사진과 이유를 저장하고 `status=retake`를 반환한다. OCR은 호출하지 않는다. 다시 찍어야 하는 이유를 보여주기 위해 파일을 남긴다.

현재 품질 규칙은 작은 이미지, 매우 어둡거나 밝은 이미지, 간단한 경계 강도 기반 흐림, 과도한 종횡비, 사방 경계 접촉을 본다. 기울기 검출 학습 모델은 앱에 붙지 않았다. 긴 영수증이나 어두운 배경이 오거절될 가능성은 실제 사진 검증 대상으로 남는다.

### 9.5 OCR 결과와 부분 결과

완전한 `OcrResult`는 done, 유용한 `PartialRead`는 needs_edit, 결과 없음은 failed로 저장된다. done은 핵심 OCR 결과가 있다는 뜻이지 사용자가 확인했고 세무 검증도 끝났다는 뜻은 아니다. confirmed는 별도 열이다.

업로드 시 제공자 원본 응답과 최초 정규화 스냅샷, 현재 편집값을 구분해 저장한다. 품목 저장은 내부에서 생성한 OCR 출처를 신뢰하는 경로로 처리한다. 일반 사용자의 수정 입력에는 같은 신뢰를 부여하지 않는다.

### 9.6 실패했을 때 파일을 지우는 경우와 남기는 경우

DB commit 전에 저장 준비가 실패하면 rollback 후 새 파일을 정리한다. 하지만 commit을 보냈는데 예외가 나면 DB에 실제로 반영됐는지 확실하지 않을 수 있다. 이때 파일을 바로 지우면 저장된 DB가 없는 사진을 가리킬 수 있어서 보존한다.

commit 후 응답 구성·refresh에 실패해도 이미 저장된 원본 파일을 지우지 않는다. 예상하지 못한 코드 오류를 단순 OCR 실패로 숨기지 않고 예외를 보존하는 처리도 있다. 이는 실패 원인을 구분하고 데이터 유실을 막기 위한 코드다.

## 10. ocr_client: 제공자 응답을 내부 계약으로 바꾸기

`parse_response()`는 먼저 JSON 객체와 images 첫 항목을 확인한다. 명시적 FAILURE를 완전 성공으로 취급하지 않는다. Document OCR의 receipt.result, 이름 붙은 Template fields, 일반 글자 fields를 분기한다.

Template에는 vendor/amount/date 등의 이름이 있으므로 이를 읽을 수 있다. General OCR은 글자를 읽었지만 의미를 정하지 않았으므로 텍스트 파싱과 좌표 KIE가 필요하다. 두 경로 모두 가능한 곳에서 `financial_from_fields()`와 `fill_from_boxes()`를 사용한다.

Document Receipt 응답 분기는 기본 상호·총액·날짜·사업자번호·품목명을 변환하는 경로다. 모든 제공자 형식에서 새 품목 좌표·수량·할인 계약이 같은 수준으로 구현되어 있다고 볼 수 없다. 현재 비교평가는 확보한 저장 응답에 대한 평가다.

`_result_from_filled()`는 원문·상호·총액·날짜가 있어야 완전 OcrResult를 만든다. 부족하면 `collect_partial()`이 이미 읽은 값·좌표·품목·검토 이유를 최대한 남긴다. 실패 응답에 유용한 fields가 있는 경우도 부분 결과로 보존할 수 있지만 완전 성공과 구분한다.

`extract_receipt()`는 설정된 URL·키를 사용해 이미지와 V2 message를 전송한다. requestId는 UUID, timestamp는 밀리초, lang은 ko다. 응답을 정상 파싱할 수 있으면 raw_response를 함께 보존한다. 현재 스프린트 설명 작업에서 이 함수를 실행하거나 외부 호출한 것은 아니다.

설정이 없거나 외부 요청 실패·파싱 실패 등에 해당하면 Windows OCR fallback을 시도한다. 임시 파일을 생성해 Windows Runtime의 OCR 엔진을 호출하고 텍스트를 가져온 뒤 정리한다. 이 경로는 CLOVA와 같은 좌표·신뢰도 정보를 모두 제공하는 경로가 아니다. 따라서 서로 다른 OCR 출력을 동일한 품질이라고 가정하면 안 된다.

## 11. KIE 전처리: 글자 상자

`TextBox`는 text, x, y, width, height, confidence, line_break를 가진 불변 dataclass다. cx/cy는 상자 중심이다.

`boxes_from_fields()`는 inferText와 boundingPoly.vertices를 읽는다. 네 꼭짓점의 최소·최대 좌표로 외접 직사각형을 만든다. 실제 다각형 모양 자체를 화면에 그대로 재현하는 방식은 아니다. 인식 신뢰도는 숫자·유한값·0~1 범위인지 확인해 보존한다.

좌표계는 원본 사진의 픽셀 기준이다. x는 왼쪽에서의 위치, y는 위쪽에서의 위치다. 화면 사진이 줄어들어도 SVG viewBox를 원본 크기로 설정하면 상대 위치가 맞는다.

`boxes_as_dicts()`는 dataclass를 저장·응답 가능한 사전으로 바꾼다. 좌표를 저장하는 이유는 행 연결뿐 아니라 사용자가 사진에서 어떤 글자를 근거로 한 값인지 확인하게 하기 위해서다.

## 12. KIE 금액 추출: 가까운 숫자보다 의미 있는 라벨

### 12.1 라벨 목록

FINANCIAL_LABELS는 과세 공급가액·면세·거래총액·결제·할인 전 합계의 라벨 후보를 분리한다. 공급가액, 면세합계, 결제금액, 주문합계가 각각 다른 필드로 들어간다.

`_financial_label()`은 공백과 일부 표시를 정리하고 정해진 라벨과 숫자 접미사 형태를 검사한다. 단순히 `합계`가 포함되었다는 이유만으로 `면세합계`를 거래 총액으로 삼지 않도록 더 엄격한 매칭을 사용한다.

### 12.2 숫자 후보 제거

전화번호, 날짜, 사업자번호, 다른 금액 라벨이 포함된 상자를 제외한다. 사업자번호 1234567890을 큰 금액으로 읽는 실수를 줄인다. `parse_amount()`는 쉼표·소수점·부호를 해석하지만 그 자체로 문맥을 판별하지 않는다. 문맥 검사는 호출하는 KIE가 수행한다.

### 12.3 _amount_near_label의 위치 우선순위

라벨 자체에 금액이 붙어 있으면 그 값을 본다. 별도 숫자라면 같은 줄 오른쪽을 우선하고, 아래쪽 가까운 후보를 차선으로 본다. 점수는 대략 다음 구조다.

```text
같은 줄 후보:      세로 거리 × 100 + 가로 거리
아래줄 후보: 100000 + 세로 거리 × 100 + 가로 거리
```

동일 행을 매우 강하게 우선하는 규칙이다. y 오차 허용은 글자 높이와 고정 픽셀 기준을 조합한다. OCR 배열에서 다음에 나온 숫자가 사진상 멀리 떨어져 있다면 가까운 값이라고 취급하지 않는다.

### 12.4 여러 후보가 충돌하면 임의로 첫 값을 고르지 않음

라벨별 값을 모아 서로 다른 숫자가 있으면 필드를 null로 남기고 `conflicting_transaction_amount_candidates` 같은 검토 사유를 남긴다. 같은 값이 여러 번 인쇄된 것은 값 하나로 모일 수 있다.

결제는 예외가 더 필요하다. 신용카드지불과 현금지불이 모두 5,000원이면 숫자 집합은 `{5000}` 하나지만 전체 결제금액 5,000원을 뜻하지 않는다. 복합 결제로 판단되면 하나의 결제금액으로 임의 선택하지 않고 검토 대상으로 남긴다. 현재 자동 결제수단 합산 엔진은 아니다.

### 12.5 주문서는 할인 전 합계일 수 있음

주문서·주문내역의 일반적인 총액을 최종 거래 총액으로 자동 승격하지 않는다. 명시적 거래총액·할인후합계·최종거래금액이 없으면 subtotal로 보존한다. 명시적 최종 금액이 있는 주문서는 그것과 일반 주문 합계를 구분한다.

### 12.6 _money_evidence

선택한 라벨과 금액 상자를 함께 출처 영역으로 연결한다. 후보 충돌은 UNREVIEWED, 라벨이 있으나 금액을 못 읽은 경우는 FAILED, 읽은 값은 READ로 기록한다. 신뢰도는 관련 상자들의 존재하는 신뢰도 중 최솟값을 사용한다. 이는 현재 구현의 보수적인 집계 규칙이며 확률 보정된 최종 정확도가 아니다.

## 13. 품목 KIE: extract_line_items를 순서대로 읽기

### 13.1 같은 행 묶기

상자를 중심 y와 x로 정렬하고 가까운 y의 상자를 같은 행으로 묶는다. 기준은 글자 높이의 약 0.65와 최소 8픽셀이다. 한 행 안에서는 x 순서로 정렬한다.

이 방식은 좌표 규칙이다. 기울기·원근·다양한 레이아웃을 학습한 모델은 아니다. 심한 기울기에서 행 연결이 나빠질 가능성은 남는다.

### 13.2 열 머리글 찾기

수량·개수, 단가·판매단가, 금액·행금액·판매금액 중 두 종류 이상이 있는 행을 헤더 후보로 삼는다. 각 헤더 중심 x를 anchors에 저장한다.

```text
상품명                  단가        수량       금액
우유                   2,000          2       4,000
```

숫자가 해당 x 열 가까이에 있으면 그 필드에 배정한다. 수량과 단가의 인쇄 순서가 바뀌어도 헤더가 있으면 위치를 따라 연결할 수 있다.

### 13.3 이름과 코드·숫자 분리

영수증 전체 폭에 대한 상대 위치로 숫자 영역과 이름 영역을 구분한다. 상품 코드·행 번호·바코드처럼 보이는 토큰은 이름 후보에서 제외한다. 날짜·사업자·주소·POS 등의 메타정보 행도 품목으로 넣지 않도록 한다.

헤더가 없고 숫자 세 개가 있으면 오른쪽 세 값을 인쇄 단가·수량·행 금액의 순서로 연결하는 fallback이 있다. 모든 영수증의 열 순서를 보장하지 못하므로 해당 조건에서의 실패도 평가에 포함된다. 숫자 두 개만 있어 수량/단가 관계가 애매하면 수량 1 등을 만들어 넣지 않는다.

### 13.4 pending: 다음 행을 기다리는 이름

상품명과 숫자 행이 분리되어 인쇄될 수 있다. 이름만 있는 행을 pending에 보존하고 가까운 뒤 행의 숫자와 합칠 수 있게 한다. 행 번호가 새로 나타나거나 거리가 멀면 이전 이름을 별도의 부분 품목으로 남길 수 있다.

이미 숫자가 있는 품목 뒤의 이름 조각을 무조건 붙이지 않는다. 괄호가 닫히지 않은 이름, 정렬, 간격 등 제한된 조건을 확인해 이어 붙인다. 그렇지 않으면 다음 상품을 앞 상품의 긴 이름으로 흡수하는 오류가 생긴다.

반복되는 `우유` 두 행은 두 품목으로 보존한다. 이름 사전으로 중복 제거하지 않는다.

### 13.5 합계·결제 행 구분

합계, 부가세, 과세·면세 물품, 공급가, 결제, 할인금액, 승인 등의 footer 표시를 만나면 품목 영역과 구분한다. 이미 시작한 품목 영역에서는 footer 이후를 종료할 수 있다.

단어 기반 규칙이므로 품목명 안에 이런 단어가 포함되는 예외나 특수 레이아웃은 한계다. 이 코드는 광범위한 영수증 형태에 대한 완전한 레이아웃 모델이 아니다.

### 13.6 숫자를 못 읽어도 품목은 남김

`1?`, 같은 열의 숫자 상자 두 개, 음수 인쇄 단가 같은 모순은 값을 비우고 FAILED 출처를 남긴다. 이름까지 버리지 않는다. 수량 절댓값이 999를 넘으면 현재 규칙에서는 수량으로 인정하지 않는다.

최종 출력은 이름·원문 이름·수량·인쇄 단가·행 금액과 필드별 출처다. 규격·단위·할인·과세 표시의 저장 계약은 있지만 이 함수가 전부 자동 추출하는 것은 아니다.

## 14. metadata: 문서의 의미를 함부로 확정하지 않기

`extract_metadata()`는 줄을 묶어 현금영수증, 카드전표, 일반 영수증, 세금계산서, 계산서의 제목 후보를 찾는다. 종류가 충돌하면 확정하지 않고 이유를 남긴다. 세금계산서·계산서의 제목을 알아본다고 전용 자동 추출을 지원한다는 뜻은 아니다.

날짜는 발견한 원문을 date_candidates에 보존한다. 공급일·발행일·결제일은 라벨이 있을 때 각각 넣는다. 의미를 모르는 날짜를 세 필드 모두에 복사하지 않는다. 거래일시에는 날짜와 시간이 모두 필요하다. 존재하지 않는 날짜, 25시 같은 시간은 정상 후보가 되지 않는다.

사업자번호는 공급받는자·고객·구매자 문맥이면 customer, 그 밖의 사업자번호 라벨이면 merchant 후보로 분리한다. 단순 OCR 문맥 규칙이므로 법적 공급자 확인을 대체하지 않는다.

승인번호와 원승인번호를 구분한다. 정규화 카드번호에 마스크가 없으면 뒤 네 자리만 남기고 마스킹한다. 이 처리는 정규화 document 필드에 적용되며 원본 사진과 raw OCR 전체를 익명화하는 기능은 아니다.

반품·취소는 제목과 음수 합계가 함께 있어야 자동 후보로 허용한다. `반품 불가`라는 안내문이나 음수 할인만으로 영수증 전체를 반품으로 분류하면 안 되기 때문이다.

## 15. 수정 저장: update_ocr의 실제 단계

### 15.1 먼저 소유권·버전·확정 여부 검사

수정 요청에는 `base_revision`이 반드시 필요하다. 서버 revision과 다르면 409 DATA_CONFLICT다. 이미 확정된 영수증의 OCR 사실은 이 경로로 다시 수정하지 못한다.

base_amount 등의 기존 비교 필드도 호환·추가 방어용으로 남아 있다. 현재 화면이 가진 전체 revision을 주된 버전 계약으로 사용한다.

### 15.2 문서 부분 수정

`_edited_document()`는 기존 문서를 읽고 전달한 부분을 합친다. 승인번호 하나를 수정한다고 다른 날짜와 카드정보를 지우지 않는다. 변경한 필드는 manual 출처로 바꾸고 기존 좌표는 대조용으로 보존한다.

원본 date_candidates를 클라이언트가 다른 원문·값·신뢰도·좌표로 바꾸려 하면 요청을 거절한다. 사용자가 새 날짜 값을 확인해 입력하는 것과 OCR 원본 증거를 다시 쓰는 것을 분리한다.

### 15.3 계산된 금액을 다시 계산

이전 값이 calculated인 경우 입력이 바뀌어도 낡은 계산 결과를 그대로 두면 합계가 깨진다. 관련 값과 명시적 수정·상태를 검사해 이전 계산값을 무효화하고 complete_money로 다시 보완한다. 수동으로 고친 다른 값은 계산이 덮지 않는다.

### 15.4 품목 저장

`_save_line_items()`는 현재 영수증의 기존 ID를 모은다. 기존 품목은 그 ID로 찾고 새 품목에는 UUID를 부여한다. 다른 영수증의 품목 ID나 요청 안의 중복 ID는 거절한다.

각 품목을 먼저 검증·준비한 뒤 삭제·재배치한다. 전달 목록에서 빠진 기존 행은 삭제 대상이다. 기존 행의 이름을 바꿔도 ID와 원문 이름을 유지한다. 순서는 새 목록 위치로 기록한다. complete_item으로 실효 단가를 다시 계산한다.

신규 line_items와 기존 items/item_amounts를 한 요청에서 동시에 수정하면 거절한다. 어느 입력을 정답으로 삼을지 불명확하기 때문이다. 신규 품목을 저장한 뒤 기존 응답에는 호환 projection을 제공한다. 이때 기존 unit_price에는 인쇄 단가를 넣어 실효 단가와 섞지 않는다.

기존 배열 방식만 수정하는 경로는 고정 ID를 완벽하게 추적할 정보가 없다. 같은 위치·같은 이름인 행만 기존 ID를 유지하는 보수적 호환 처리를 사용한다. 신규 구조화 화면으로 전환한 이유가 여기에 있다.

### 15.5 최종 UPDATE도 조건부로 수행

함수 처음에 revision을 확인했어도 그 다음 순간 다른 세션이 저장할 수 있다. 그래서 최종 SQL UPDATE의 WHERE에도 소유권, revision, 미확정 상태, 읽고 검사한 금액·품목 등 조건을 넣는다.

한 행이 실제로 바뀌었는지 rowcount로 확인한다. 0이면 stale 상태라고 보고 rollback하고 409를 반환한다. 이것이 비교 후 변경을 한 SQL 조건으로 묶는 CAS 방식이다.

영수증 수정, 품목 변경, 할인 참조 검사, 중복 후보 갱신은 같은 DB 트랜잭션에 있다. 품목 ID가 잘못되거나 중복 갱신이 실패하면 앞서 바꾼 revision·상호도 같이 되돌린다. 절반만 저장되는 것을 막는다.

## 16. OCR 확정: confirm_receipt

확정 입력에도 base_revision이 필요하다. retake를 확정할 수 없고 상호·날짜·기본 총액, 필요한 금액 상태·합계 관계를 검사한다. 핵심 후보가 UNREVIEWED면 사람이 읽은 값으로 확인하기 전에는 확정하지 못한다.

반품·취소는 음수 총액과 성분 부호를 보존해 검사한다. 일반 거래의 음수 금액을 반품 문서 없이 허용하지 않는다.

품목의 수량·인쇄 단가가 실제 미기재인 경우까지 채우라고 강요하지 않는다. 누락 수량 1을 만들어 확정시키는 것보다 부분 품목을 유지하는 편이 맞다.

최종 UPDATE는 revision, 미확정, retake 아님, 검사한 상호·날짜·금액·품목 상태가 여전히 같은지를 다시 조건으로 검사한다. 성공하면 confirmed=true, status=done, revision+1이다. 그 DB 트랜잭션 안에서 필요한 Transaction을 생성하고 receipt에 연결한다. 거래 생성 실패면 확정도 rollback된다.

### 16.1 두 화면 경합을 실제 숫자로 이해하기

```text
A가 영수증 revision=5, 거래총액=11,000을 조회
B가 5,000원으로 수정 저장 → revision=6
A가 base_revision=5로 확정 요청
 → 409, 확정되지 않음
 → 화면이 최신 revision=6과 5,000원을 다시 조회
 → A가 최신 금액을 보고 맞을 때만 다시 확정
```

확정이 먼저 성공한 경우, 뒤늦은 수정은 미확정 조건 또는 revision 조건에서 거절된다. 핵심은 검사한 상태와 바꾸는 상태를 DB 조건으로 연결했다는 점이다. 단순히 Python에서 한 번 비교한 것만으로 경합을 막았다고 설명하면 안 된다.

### 16.2 OCR 확정과 증빙 유효성은 다름

OCR 확정은 읽은 사실을 사용자가 확인했다는 상태다. 증빙 유형별 정보가 부족해 evidence_validation이 INCOMPLETE인 영수증도 OCR 사실 확인과는 다른 문제일 수 있다. 현재 확정 함수가 모든 증빙 필드를 VALID로 만든 다음에만 확정하는 것은 아니다.

`tax_analysis_confirmed=False`, `deduction_status=UNDETERMINED`를 유지한다. 외부 사업자 검증도 NOT_PERFORMED다. 세법 판단을 구현했다고 주장하지 않는다.

## 17. 증빙 검증: evidence_validation

핵심 상호·날짜·사업자번호, 문서 종류, 문서별 필수정보, 네 금액과 상태를 검사한다. 카드·현금영수증에는 승인번호, 세금계산서·계산서에는 발행일·고객 사업자번호 등을 요구한다. 번호 형식과 merchant/core 사업자번호 불일치도 확인한다.

우선순위는 `INVALID → CONFLICT → INCOMPLETE → VALID`이다.

- INVALID: 허용하지 않은 음수나 형식 등 잘못된 사실.
- CONFLICT: 값 간 모순, 후보 충돌, 합계 불일치.
- INCOMPLETE: 필수 정보 누락·미확인.
- VALID: 구현된 로컬 정보 검사 기준을 통과.

VALID는 외부 사업자 조회나 공제 판단이 완료됐다는 뜻이 아니다. 거래 검증은 연결된 영수증들의 금액·사업자번호 충돌도 따로 모아서 상태를 합친다.

## 18. 거래 API와 대표 증빙

`create_from_receipt()`는 확정 영수증에서 거래 facts를 만든다. 일반 거래는 NEEDS_CONTEXT, 원거래가 없는 반품은 UNRESOLVED_ADJUSTMENT다. OCR 확인 true, 세무분석 확인 false로 기록한다.

`transaction_out()`은 거래 facts, 연결된 영수증, 대표 증빙 ID, 대표 품목, 증빙 검증 결과를 함께 반환한다. `integration_status=LOCAL_CONTRACT_ONLY`는 팀 외부 파트와 실제 연결된 상태가 아니라 로컬 데이터 계약이라는 뜻이다.

GET line-items는 연결된 모든 증빙의 행을 receipt_id와 함께 조회하는 API다. 대표 품목만 제공하는 canonical_line_items와 구분해야 한다. 모든 증빙 행을 구매 품목으로 합치면 중복 구매가 된다.

품목 용도 수정은 Transaction의 revision을 검사한다. 변경 후 해당 Receipt revision도 증가시켜 다른 화면이 오래된 품목 상태로 저장하지 못하도록 한다. 용도 입력이 BUSINESS라고 해서 자동으로 공제 가능 판정을 내리지는 않는다.

## 19. 사진 해시와 중복 후보

### 19.1 SHA-256과 pHash

SHA-256은 파일 바이트가 같으면 같다. JPEG를 다시 저장하면 사진이 비슷해도 SHA는 달라질 수 있다.

pHash는 EXIF 방향을 적용하고 grayscale 32×32로 줄인 뒤 저주파 DCT 성분을 계산한다. DC를 제외한 성분의 중앙값보다 큰지로 비트를 만든다. XOR 결과의 bit_count가 두 해시의 Hamming 거리다. 현재 거리가 6 이하이면 유사 이미지 후보다.

pHash는 닮은 이미지 탐색 기준이고 같은 거래의 증명은 아니다. 형식이 비슷한 다른 영수증도 닮을 수 있다. 실제 재촬영 쌍에 대한 재현 성능은 아직 따로 입증되지 않았다.

### 19.2 duplicate_reason의 우선순위

동일 SHA면 SAME_FILE, 가까운 pHash면 SIMILAR_IMAGE, 승인번호·거래일시·사업자번호·거래총액이 모두 있고 같으면 SAME_APPROVAL_SIGNATURE다. 자동 삭제·병합은 하지 않는다.

### 19.3 find_duplicates와 동시 후보 생성

같은 사용자의 다른 영수증만 비교한다. 현재는 전체 스캔이며 대규모 검색 인덱스 구현은 아니다. 두 영수증 ID를 작은 ID/큰 ID 순서로 정렬해 쌍을 고정한다. DB에는 쌍 고유 제약이 있다.

동시에 같은 후보가 생기면 SQLite/PostgreSQL의 upsert로 하나의 후보를 유지한다. 기존 사용자가 해결한 action/reason을 새 자동 후보가 덮지 않는다. 이 구현의 중복 저장 경로는 이 두 DB dialect를 명시적으로 지원한다.

기존 파일의 해시가 없는 경우 backfill_image_fingerprints로 보완한다. 파일 없음, 기존 SHA와 내용 불일치, 처리 중 변경은 건너뛰고 이유를 남긴다. 이 함수 자체가 OCR을 호출하거나 사진을 다시 쓰지는 않는다. commit은 호출자의 책임이다.

## 20. MERGE와 SEPARATE

SEPARATE는 별도 거래로 유지하기로 결정하는 것이다. 두 Receipt와 Transaction은 남는다.

MERGE는 대표 거래를 선택해 다른 거래의 증빙을 옮긴다. 두 일반 거래의 알려진 금액·사업자번호가 다르면 거절한다. 거래 revision과 이동하는 모든 Receipt revision을 검사한다. 하나라도 바뀌면 전체를 rollback한다.

source 거래는 삭제하지 않고 workflow_status=MERGED와 merged_into를 기록한다. 대표 금액에 source 금액을 더하지 않는다. 기존 증빙 파일과 품목은 보존한다.

반품이 연결된 원거래를 병합하면 연결된 조정거래도 대표 원거래로 옮겨야 한다. 합친 반품 금액이 대표 원거래 금액을 넘는지 먼저 검사한다. 사용자 후보 해결 표시도 병합 실패 시 함께 rollback한다.

## 21. 반품·취소·조정 처리

### 21.1 수동 조정거래

POST adjustments는 원거래에 음수 반품·취소를 기록할 수 있다. 원거래 버전을 갱신해 다른 반품 추가와 직렬화하고 기존 조정액을 합산한다. 반품/취소는 총액 음수, 입력된 성분은 양수 금지다. 세 금액이 모두 있으면 합계를 정확히 확인한다.

증빙을 아직 연결하지 않은 수동 조정은 NEEDS_EVIDENCE, ocr_confirmed=false다. API가 있다고 현재 화면에 수동 조정 생성 폼까지 있다는 뜻은 아니다. TransactionPage는 이미 존재하는 조정과 연결 흐름을 다룬다.

### 21.2 원거래 없는 반품 사진

반품 사진을 읽고 OCR을 확정하면 Transaction은 생기지만 원거래를 자동 추측하지 않는다. UNRESOLVED_ADJUSTMENT로 남긴다. 사용자가 원거래를 선택하면 거래처·부호·잔액과 두 거래 revision을 확인해 연결한다.

### 21.3 반환 한도

```text
원거래 +10,000
기존 반품 -3,000
새 반품 -8,000
 → 합계 -1,000, 원거래 초과이므로 거절
```

검사는 MERGED가 아닌 연결 조정거래를 합산한다. 실제 세법상 환불 판단을 하는 규칙은 아니고 데이터 중복·초과 조정을 방어하는 로컬 규칙이다.

### 21.4 수동 반품과 실제 반품 사진의 중복 차감 방지

수동 -3,000원 조정이 이미 있고 나중에 -3,000원 반품 영수증을 OCR 확정하면 두 조정 거래가 생길 수 있다. 두 거래를 별도 반품으로 두면 -6,000원을 차감하게 된다.

`link_adjustment_evidence()`는 같은 종류·금액·거래처·날짜 관계를 확인하고 사진 증빙을 기존 조정 거래로 옮긴다. OCR로 생성된 source 조정 거래는 MERGED로 남겨 한 번만 집계한다. 원거래·대상·source의 revision을 검사해 새 반품 추가와 겹쳐도 연결을 보호한다.

## 22. 프론트 API 계층

`api/receipts.ts`는 요청 함수와 ReceiptApi/StructuredItem/DocumentFacts/Evidence 타입을 정의한다. TypeScript 타입은 개발 중 오류를 찾는 도구이고 서버의 런타임 입력 검사를 대체하지 않는다.

사진은 `responseType:"blob"`으로 인증 API에서 받는다. 브라우저 img에 저장 키를 직접 공개 주소처럼 넣지 않는다. 업로드는 FormData, 수정은 PATCH, 확정은 최신 saved.revision을 담은 POST다.

`api/transactions.ts`는 조회·용도 변경·원거래 연결·중복 해결·증빙 연결을 감싼다. 연결 요청에는 대표·source·원거래·하위 조정·영수증 버전이 필요한 만큼 포함된다. 관련된 여러 레코드를 한 번에 변경하기 때문에 단일 ID만 보내는 것으로 충분하지 않다.

## 23. OcrResultEditPage: React 상태를 따라 이해하기

### 23.1 서버 데이터와 입력 문자열 분리

`receipt`는 마지막으로 읽은 서버 객체다. 상호, 금액, 날짜, 품목 rows, document, discounts는 편집 상태다. 숫자 입력은 문자열로 보관한다. 사용자가 빈칸·소수점·잘못된 문자를 입력하는 중간 상태를 숫자 하나로 표현하기 어렵기 때문이다.

`baseMoney`는 조회 시의 비교 금액이다. `ready`는 초기 조회 완료, `saving`은 요청 중, `needsRefresh`는 최신 상태를 다시 확인해야 한다는 표시다.

`fillForm()`은 서버 응답을 모든 입력에 반영하고 임시 fieldStates를 초기화한다. 충돌 후 최신 값으로 칸을 다시 채우는 핵심 함수다. schema2 또는 신규 금액이 있으면 분리 금액 화면을 선택한다.

### 23.2 숫자 파싱

`parseNumber()`는 쉼표를 제거하고 정규식과 Number.isFinite로 검사한다. `10O00`은 알파벳 O가 있어 오류다. 빈칸은 null, 숫자 0은 0이다. signed=true일 때 음수 입력을 허용한다. 최종 금액 의미·부호 검사는 서버가 다시 수행한다.

### 23.3 저장과 확정 두 단계

`handleConfirm(false)`는 저장하고 계산된 서버 응답을 다시 보여준다. `handleConfirm()`은 품목·문서·금액을 파싱해 PATCH하고, 응답을 fillForm한 다음 그 saved.revision으로 확정한다. 성공하면 보관함으로 이동한다.

처음 조회한 revision을 확정에 그대로 사용하지 않는다. PATCH 저장으로 revision이 올라갔기 때문이다. 저장과 확정 사이 다른 세션이 수정하면 새 revision 검사로 충돌이 된다.

### 23.4 실패 세 종류

1. 클라이언트 입력 오류: 아직 서버 저장 전이므로 입력 유지. 서버 재조회로 사용자의 초안을 지우지 않음.
2. 409 DATA_CONFLICT: 최신 서버 상태를 다시 읽고 fillForm. 조회 실패면 needsRefresh를 유지해 추가 저장·확정을 잠금.
3. 확정 요청의 네트워크/5xx: 서버가 확정했지만 응답만 실패했을 수 있음. 무작정 재확정하지 않고 최신 상태 확인을 요구.

`inputDisabled`는 ready/saving/needsRefresh/confirmed를 합쳐 결정한다. 이미 확정된 영수증에서는 거래 화면으로 이동할 수 있다.

### 23.5 useEffect의 active 플래그

컴포넌트가 다른 영수증으로 이동하거나 사라진 뒤 늦게 도착한 응답이 이전 화면 상태를 덮지 않도록 active를 검사한다. 이 플래그는 실제 네트워크 요청 취소 자체와는 다르다.

## 24. ReceiptReview: 사진과 품목 행 편집

`ItemDraft`는 서버 품목 숫자 필드를 문자열로 바꾸고 화면 전용 key를 더한 타입이다. 기존 서버 ID가 있으면 key로 사용하고 새 품목은 임시 UUID를 쓴다. 임시 React key와 서버 저장 ID는 역할이 다르다.

사진 Blob에서 Object URL을 만들고 unmount/영수증 변경 시 revoke해 브라우저 메모리를 정리한다. naturalWidth/Height를 읽어 SVG viewBox를 맞춘다. 선택한 품목의 sources.boxes를 rect로 그린다. 선택 위치로 스크롤도 이동한다.

품목 수정은 map으로 해당 행만 새 객체로 바꾸고, 이동은 배열을 복사해 순서를 바꾼다. 품목 추가·삭제·위아래 이동이 서버 ID와 분리되어 있다. 선택 행의 모든 출처 영역이 표시되므로 계산값의 입력 영역도 함께 보일 수 있다.

실효 단가는 입력해서 조작하는 값이 아니라 저장 후 서버가 계산한 값을 보여준다. 품목 규격·단위·과세 표시·사용 용도는 편집할 수 있다. 모든 필드가 자동 KIE에서 채워지는 것은 아니다.

## 25. DiscountEditor와 거래 화면

할인 화면은 적용 범위에 따라 저장된 품목 ID 선택지를 보여준다. 새 품목은 서버 ID가 생긴 뒤 연결할 수 있으므로 먼저 저장하게 안내한다. 할인 삭제 시 그 할인을 포함 대상으로 참조한 관계도 비워 고아 참조를 줄인다. 서버가 순환·존재·범위를 최종 검사한다.

TransactionPage는 현재 거래·전체 거래·중복 후보를 함께 읽는다. save 래퍼는 busy로 중복 클릭을 막고 성공 후 최신 상태를 다시 조회한다. 409도 최신 조회를 시도한다.

일반 거래에는 같은 거래의 다른 증빙 연결, 미해결 반품에는 원거래 연결, 이미 원거래에 붙은 조정에는 반품 증빙 연결을 제공한다. UI가 고른 후보도 서버에서 다시 검증한다. 서로 다른 금액을 같은 거래로 묶는 결정을 UI만 믿지 않는다.

중복 후보에는 사진 대조 링크, 별도 유지, 현재 거래로 병합이 있다. 반품·MERGED·미확정 거래 등 현재 병합하면 안 되는 선택은 버튼 조건으로 제한한다.

## 26. 보관함 합계가 중복 증빙을 제외하는 방법

PurchaseStoragePage는 영수증과 거래를 함께 조회한다. MERGED와 UNRESOLVED_ADJUSTMENT를 제외한 거래의 대표 증빙 ID 집합을 만든다. 확정된 대표 증빙만 합계에 포함하고 같은 거래의 다른 증빙은 목록에 남기되 합계 제외로 표시한다. 원거래에 연결된 음수 반품 대표 증빙은 합계에 반영할 수 있다.

미확인 숫자를 UI 계산 편의를 위해 0으로 표현하는 일부 view-model 필드는 DB의 실제 0과 같지 않다. amountMissing/supplyMissing/vatMissing 표시도 함께 둔다. 또한 사진이 없는 수동 조정거래까지 이 보관함의 Receipt 기반 합계가 완전하게 집계하는 구조는 아니다. 거래 사실 전체를 집계하는 회계 보고서와 구분해야 한다.

StorageView는 목록·필터·합계를 렌더링하는 공통 컴포넌트다. 이번 매입 화면은 disablePdf로 PDF를 추후 지원 표시한다. 기존 월 필터와 다른 mock 화면 등은 별도 기존 UI가 남아 있을 수 있으며 앱 전 화면이 실제 세무 데이터로 통합됐다는 뜻은 아니다.

## 27. API 경로 한눈에 보기

| 메서드·경로 | 기능 |
|---|---|
| POST `/receipts` | 사진 업로드와 판독 |
| GET `/receipts` | 소유한 영수증 요약 목록 |
| GET `/receipts/confirmed` | OCR 확정 영수증 상세 목록 |
| GET `/receipts/{id}` | 사진 대조용 영수증 상세 |
| GET `/receipts/{id}/image` | 인증·소유권 검사 후 원본 사진 |
| PATCH `/receipts/{id}/ocr` | revision을 요구하는 수정 |
| POST `/receipts/{id}/ocr/confirm` | revision을 요구하는 OCR 확정 |
| GET `/transactions`, `/{id}` | 소유한 거래 조회 |
| GET `/transactions/{id}/evidence` | 연결 증빙 목록 |
| POST `/transactions/{id}/evidence/validate` | 로컬 증빙 검사 |
| POST `/transactions/{id}/evidence` | 다른 증빙/거래 연결 |
| GET `/transactions/{id}/line-items` | 모든 연결 증빙의 품목 조회 |
| PATCH `/transactions/{id}/line-items/{item_id}` | 품목 용도·메모 수정 |
| POST `/transactions/{id}/adjustments` | 수동 조정 생성 |
| PATCH `/transactions/{id}` | 미해결 조정 원거래 연결 |
| GET `/reconciliation/issues` | 소유한 중복 후보 조회 |
| POST `/reconciliation/issues/{id}/resolve` | MERGE/SEPARATE 결정 |

사진 응답은 private,no-store와 nosniff를 사용한다. 인증 파일 조회라는 경로와 저장 키는 서로 다르다. 목록 응답은 ReceiptSummary이므로 상세 화면은 GET 상세를 사용해야 한다. 프론트 listReceipts의 타입 표기만 보고 목록에 모든 상세 필드가 있다고 가정하지 않는다.

## 28. migration: 기존 데이터를 지키면서 구조 추가

| revision | 하는 일 |
|---|---|
| 20261005a1 | 분리 금액 열과 money_sources_json 추가 |
| 20261005a2 | 할인 전 합계·기존 품목 숫자 JSON·금액 계약 버전 추가 |
| 20261005a3 | Transaction·LineItem·중복 후보 테이블, 출처·원본 응답·해시·revision·거래 FK 추가 |
| 20261005a4 | 과거 확정 영수증의 거래 연결 보완 |
| 20261005a5 | 중복 후보 active와 쌍 unique 제약 추가 |
| 20261005a6 | main의 사업자 프로필 이력과 Document AI 이력을 단일 head로 연결 |

a1/a2는 기존 amount/supply를 새 과세/면세 값으로 강제 변환하지 않는다. a3는 기존 items_json과 item_amounts_json을 읽어 품목 행을 생성한다. 기존 계산 단가는 인쇄 단가로 승격하지 않는다. 과거 행 ID는 receipt/position을 입력한 UUID5로 결정적으로 만든다.

a4는 confirmed이고 transaction_id가 없는 과거 영수증만 연결한다. 기존 연결이 있으면 건너뛴다. 금액·확정·revision·status를 새 사실처럼 다시 작성하지 않는다. 음수 기존 사실은 미해결 조정 상태로 보존한다. downgrade가 연결 기록을 지우지 않도록 되어 있어 이후 사용자 연결·수정을 보존한다.

upgrade 테스트와 기존 DB 보존 기록은 스키마 변경 안전성을 확인한 증거다. 모든 데이터셋의 OCR 정확도나 모든 DB 종류의 완벽한 migration을 증명하지 않는다.

## 29. 동일 캐시 비교평가: evaluation.py

### 29.1 입력과 비교 조건

test_dataset.jsonl에는 사진별 정답, printed 인쇄값, derived 계산값, 품목 정답이 있다. before_document_ai.json에는 기존 예측과 캐시 경로·SHA가 있다. run은 캐시 SHA를 먼저 비교한다. 응답이 달라졌으면 같은 OCR 조건 비교가 아니므로 중단한다.

existing은 보존한 기존 예측, improved는 현재 parse_response/collect_partial로 같은 응답을 해석한 결과다. 따라서 이 비교는 원본 사진에 새 OCR을 수행한 실험이 아니라 같은 OCR 응답의 후처리 비교다. existing도 엄밀히 모든 제공자의 원시 문자 정확도 자체를 의미하지 않는다. 문자 CER/WER 전용 평가도 아니다.

### 29.2 printed와 derived를 섞지 않기

사진에 공급가액이 없지만 총액·면세·VAT로 계산할 수 있다면 OCR 인쇄값 정답은 null이고 계산 규칙 정답은 derived 값이다. 계산값을 인쇄값 정답으로 넣으면 보이지 않는 글자를 OCR이 못 읽었다고 벌점을 주게 된다.

calculation_rules 평가는 정답 인쇄 금액을 계산기에 넣은 별도 규칙 평가다. OCR의 잘못 읽은 입력까지 포함한 end-to-end 계산 성능이 아니며 OCR 점수에 합산하지 않는다.

### 29.3 TP/FP/FN 계산

정답과 예측이 같고 정답이 존재하면 TP다. 다른 값이 출력되면 FP, 있어야 할 정답을 못 맞추면 FN이다. 정답 10,000에 예측 1,000이면 FP와 FN이 동시에 1이다. 정답 null에 예측 0이면 FP다.

```text
Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
F1        = 2TP / (2TP + FP + FN)
금액 정확 일치율 = 인쇄 정답이 있는 값 중 정확히 같은 비율
```

normalize는 문자열 NFKC와 공백 제거, 숫자 Decimal 표기를 이용한다. 모든 상호의 유사표기·동의어를 자동 동등 처리하지는 않는다.

### 29.4 품목 일대일 연결

예측 이름과 정규화된 정답 이름이 정확히 같은 행을 미매칭 목록에서 하나 소비한다. 반복 품목은 각각 다른 정답 행과 연결된다. 그 행의 수량·인쇄 단가·행 금액만 비교한다.

우유 행에 빵의 4,000원이 잘못 붙어도 다른 행 어딘가에 4,000원이 있다는 이유로 성공으로 세지 않는다. 전체 행 성공은 이름과 세 숫자가 같은 행에서 맞아야 한다. 실제 미기재 숫자는 비어 있어야 성공이다.

현재 이름 기반 정확 매칭은 순서를 이용한 최적 연결이나 fuzzy matching이 아니다. 같은 이름을 여러 번 샀고 수량이 다르면 반복 행의 매칭 순서도 성능 해석에 영향을 줄 수 있다.

### 29.5 correction_needed

필드 오류 또는 품목 오류가 하나라도 있으면 해당 영수증은 수정 필요다. 실제 사용자 행동을 관찰한 수정률이나 평균 수정 시간은 아니다. 평가의 엄격한 정답 기준에서 오류가 있는 영수증 비율이다.

### 29.6 현재 저장 보고서 결과

| 지표 | 기존 | 개선 |
|---|---:|---:|
| 상호 정확 일치율 | 0.300 | 0.300 |
| 사업자번호 정확 일치율 | 1.000 | 1.000 |
| 거래일 정확 일치율 | 0.733 | 0.733 |
| 과세 공급가액 정확 일치율 | 0.136 | 0.364 |
| 면세금액 정확 일치율 | 0.235 | 0.647 |
| VAT 정확 일치율 | 0.682 | 0.773 |
| 거래총액 정확 일치율 | 0.357 | 0.571 |
| 결제금액 정확 일치율 | 0.067 | 0.400 |
| 품목명 F1 | 0.000 | 0.676 |
| 품목 전체 행 F1 | 0.000 | 0.511 |
| 수정 필요 비율 | 1.000 | 1.000 |

정답 품목 111행, 개선 추출 108행, 이름 연결 74행, 숫자까지 전체 정확한 행 56행이다. 품목명 F1 0.676이 서비스 전체 정확도 67.6%라는 뜻은 아니다.

사용자는 기존 판독값을 대략 수용했지만 확장된 추가 정답의 독립 검증은 끝나지 않았다. 제외 0건, 30건의 잠정 Baseline이다. 상호가 낮은 문제는 전처리·OCR 오인식·KIE 선택·정답 표현을 실제 사진과 응답으로 나눠 봐야 한다. 단순 토큰 부재 진단을 확정적인 원인 분석으로 사용하면 안 된다.

## 30. quality_experiment: 모델이 하는 일과 하지 않는 일

모델의 출력은 글자나 품목이 아니다. 흐림·저조도·잘림·기울기 네 결함의 점수다. 네 결함은 동시에 존재할 수 있으므로 서로 배타적인 softmax 5분류가 아니라 네 출력 sigmoid/BCE 다중 라벨 문제다. 정상은 네 결함이 모두 없는 상태다.

### 30.1 분할과 누수 방지

원본 사진을 읽어 SHA를 확인하고 동일 SHA, pHash 거리, 사업자·날짜·총액 서명으로 유사 원본 그룹을 묶는다. 그룹을 train/validation/test 18/6/6 목표로 나눈다. 모든 증강본은 같은 원본 분할에 남긴다. 그룹 크기 때문에 일반적인 데이터에서는 정확한 비율을 보장하지 않을 수 있으며 manifest에 실제 개수를 기록한다.

사진을 먼저 변형해서 비슷한 사진을 train과 test에 나눠 넣으면 원본 내용이 새어 실험 점수가 과대평가될 수 있다. 원본 단위로 먼저 분할하는 이유다. 실제 재촬영 사진의 같은 거래 여부를 이 자동 그룹 기준만으로 완벽히 아는 것은 아니다.

### 30.2 전처리와 증강

224×224 letterbox로 전체 영수증을 남긴다. center crop으로 머리글·합계가 사라지는 것을 피한다. RGB/255 후 ImageNet 평균·표준편차로 정규화한다.

네 결함의 16조합을 생성한다. train은 강도를 무작위로 선택하지만 이번 코드는 만들어 둔 학습 텐서를 여러 epoch 사용하는 방식이며 매 epoch 새 증강을 다시 생성하는 것은 아니다. validation/test는 고정 조건이다.

Gaussian blur, 밝기 감소, 윗부분 자르기, 흰 배경 회전은 인위적 조건이다. 실제 손떨림·감열 인쇄 탈색·원근·배경·촬영 오류의 모든 분포를 대표하지 않는다. 무변형 원본도 독립 검토된 정상 사진이라고 확정되지 않았다.

### 30.3 SmallCNN

```text
RGB 3채널
 → Conv(3→12, 5×5, stride2), ReLU, MaxPool
 → Conv(12→24, 3×3, stride2), ReLU
 → Conv(24→32, 3×3, stride2), ReLU
 → AdaptiveAvgPool(1×1), Flatten
 → Linear(32→4)
```

Conv는 주변 픽셀 패턴을 학습하고 ReLU는 비선형성을 넣는다. pool/stride는 공간 크기를 줄인다. global average는 위치별 특징을 채널 대표값으로 만들고 head는 네 결함 logit을 출력한다. 처음부터 무작위 초기화로 20 epoch 학습한다.

### 30.4 MobileNetV3-Small

ImageNet 사전학습 모델의 classifier를 Identity로 바꾸고 backbone 파라미터 requires_grad=false로 고정한다. train/validation 특징을 미리 계산하고 네 출력 Linear head만 100 epoch 학습한다. 전체 MobileNet을 fine-tuning한 실험이 아니다. 추론에는 backbone+head를 함께 사용한다.

### 30.5 학습과 임계값

Adam lr=.002, BCEWithLogitsLoss, batch16이다. 모델 출력은 logit이고 평가에서는 sigmoid로 점수를 만든다. validation loss가 가장 낮은 epoch의 파라미터를 복원한다. 결함별 임계값은 validation의 F1을 기준으로 .1~.9 범위에서 .05씩 탐색한다. 동점이면 현재 튜플 비교 방식으로 높은 임계값을 택한다. test로 임계값을 정하지 않는다.

seed와 결정적 알고리즘, CPU thread4를 설정하고 checkpoint 해시를 기록한다. 이 설정은 재현성을 돕지만 다른 라이브러리 버전·하드웨어에서 bit 단위 완전 동일 결과를 일반적으로 보증하는 선언은 아니다.

### 30.6 현재 보고서의 정확한 범위

| 방식 | 흐림 F1 | 저조도 F1 | 잘림 F1 | 기울기 F1 | 무변형 참고 오거절 |
|---|---:|---:|---:|---:|---:|
| CNN | .667 | .980 | .730 | .873 | .500 |
| MobileNet | 1.000 | .921 | .918 | 1.000 | .000 |
| 앱 규칙 | .842 | .400 | .390 | .000 | .167 |

이 점수는 인위적 조건의 참고 점수다. test 원본 6장에 16조건을 적용한 96장이지 실제 독립 사진 96장이 아니다. 실제 품질 gold 0/30, 실제 결함 F1과 실제 정상 오거절률은 미측정이다. 모델을 앱에 적용하거나 MobileNet이 실제 서비스에서 우수하다고 확정할 근거는 아직 부족하다.

동일 PNG 메모리 입력에서 decode+전처리+판정 중앙값은 CNN138.37ms/Mobile158.54ms/규칙193.23ms다. native 해상도 규칙과 224 모델 전처리는 다르다. 디스크·네트워크·이미지 인코딩은 제외했고 모델만의 시간은 별도 항목이다. 휴대폰 실제 지연이나 운영 서버 처리량을 의미하지 않는다.

### 30.7 실제 사진 시각 초안 보호

attach_visual_candidates는 ID, 사진 이름, SHA, split, 네 boolean 라벨, ASSISTANT_DRAFT/independent=false를 확인한다. 초안을 real_labels로 승격하지 않는다. 학습·임계값·실제 성능 계산에서 제외한다. OCR 정답을 수용했다는 사실과 품질 라벨의 독립 검증은 별개다.

## 31. 테스트를 읽으면 무엇을 확인할 수 있나

| 테스트 파일 | 중요한 시나리오 |
|---|---|
| test_receipts.py | 업로드·파일 보존·부분 판독·금액 저장·확정 경합·소유권 |
| test_document_ai.py | 품목 ID와 순서, 반복 품목·소수 수량·줄바꿈, 출처·신뢰도, 날짜 후보, 충돌 금액·복합 결제, 빈 값 상태 |
| test_transactions.py | 확정 후 거래, 용도 revision, 후보만 생성, 병합/별도 유지, 반품 한도, 증빙 연결, 병합 후 반품 이동, 원자성 |
| test_migrations.py | 신규 schema 생성, 기존 금액·확정 기록·거래 연결 보존 |

테스트를 읽을 때 Arrange(초기 상태)→Act(함수/API 호출)→Assert(기대 결과)를 구분한다. monkeypatch로 OCR 출력을 고정했다면 실제 OCR 정확도 테스트가 아니라 앱 처리 테스트다. 임시 SQLite로 경합을 재현한 테스트는 그 DB와 테스트 조건의 동작을 확인한다. 모든 운영 DB의 부하·교착·성능 검증까지 의미하지 않는다.

대표적으로 `test_structured_items_preserve_identity_through_name_and_order_changes`는 이름/순서를 바꿔도 ID가 유지되는지, `test_unknown_item_id_rolls_back_revision_and_other_edits`는 잘못된 품목 ID에서 앞선 변경이 같이 되돌아가는지 본다. `test_split_cash_and_card_are_not_mistaken_for_whole_payment`는 현금+카드 한쪽을 총결제금액으로 고르지 않는지 본다.

`test_original_merge_rejects_combined_excess_refunds_without_changing_links`는 원거래 병합 뒤 반품이 초과하면 링크까지 보존되는지 본다. `test_confirm_holds_the_row_until_save_so_overlap_cannot_confirm_mismatch`는 수정과 확정이 겹치는 짧은 구간을 자동으로 재현하는 회귀 테스트다. 사람이 마우스 두 개로 타이밍을 맞추는 검사보다 의도한 경합을 안정적으로 만들 수 있다.

## 32. 한 영수증을 끝까지 따라가는 예시

실물에 우유 2개, 인쇄 단가2,000원, 할인 후 행금액3,000원, 면세0원, VAT273원, 과세 공급가액2,727원, 거래총액3,000원이 있다고 가정한다. 이 예시는 코드 이해용이며 Dataset의 특정 사진을 새로 판독한 결과가 아니다.

1. 업로드 파일 검사를 통과하고 원본을 사용자 디렉터리에 저장한다.
2. 품질 규칙이 통과하면 OCR을 요청한다.
3. fields를 TextBox로 만들고 헤더 x/행 y로 우유·2·2,000·3,000을 연결한다.
4. printed_unit_price=2000, quantity=2, line_amount=3000으로 저장한다.
5. complete_item은 effective_unit_price=1500을 calculated 출처로 만든다.
6. 금액 라벨을 이용해 2727+0+273=3000을 확인한다.
7. 수정 화면에서 우유 행을 선택하면 관련 상자가 사진에 표시된다.
8. 사용자가 이름을 저지방 우유로 바꾸면 고정 품목 ID는 유지되고 name 출처는 manual이 된다.
9. PATCH 성공으로 receipt revision이 증가하고 계산값을 다시 보여준다.
10. 그 응답의 revision으로 OCR 확정한다. 필요한 금액과 미확인 여부를 검사한다.
11. Transaction을 생성하고 같은 DB commit에서 연결한다.
12. 같은 구매의 카드전표를 따로 올리면 새 Receipt가 생길 수 있지만 명시적 연결 후 구매 합계는 한 번만 센다.
13. 반품1,000원이 있으면 원거래와 별도 조정 Transaction -1000으로 연결한다. 원거래 사실을 2000으로 덮어쓰지 않는다.

## 33. 아직 남은 것과 구현을 과장하면 안 되는 부분

- 품목 구조와 화면은 구현됐지만 자동 규격·단위·품목 할인·과세 표시 추출이 모두 완성된 것은 아니다.
- 잠정 Baseline에서 상호·거래총액·결제금액의 오차와 품목 연결 실패가 남고 30건 모두 엄격한 수정 필요 기준에 걸린다.
- 확장 정답 독립 검증과 실제 품질 라벨 검증이 끝나지 않았다.
- 실제 재촬영 쌍에 대한 pHash 재현 성능과 정상 사진 오거절률을 입증하지 못했다.
- 학습 모델은 실험 전용이며 앱에는 기존 규칙만 들어간다.
- 전처리한 사진을 새 OCR로 비교하지 않았으므로 OCR 개선 효과를 주장하지 않는다.
- 증빙 로컬 검사와 OCR 확정은 외부 사업자 검증·세법상 적격성·공제 가능성 확정이 아니다.
- 거래 연결 계약은 로컬에서 동작하지만 실제 팀 RAG/Rule Engine 통합은 별도다.
- 모델 Test 원본6건과 한국 영수증30건은 다양한 상점·촬영환경을 대표하기에 작다.

## 34. 스스로 설명할 수 있는지 확인하는 질문

1. 영수증 사진 두 장과 구매 거래 두 건은 왜 같지 않은가?
2. 인쇄 단가와 실효 단가가 다른 예시를 계산할 수 있는가?
3. None, 0, ABSENT, FAILED는 어떻게 다른가?
4. 총액11,000만으로 VAT1,000을 확정하면 왜 위험한가?
5. 함수 시작의 revision 비교만으로 동시 수정이 막히지 않는 이유는?
6. 저장 응답 revision을 확정에 보내야 하는 이유는?
7. 409와 숫자 입력 오류에서 화면이 다르게 동작하는 이유는?
8. 두 품목에 같은 금액이 있을 때 행 연결 성능을 어떻게 세는가?
9. pHash가 가까우면 자동 병합해도 되는가?
10. 수동 반품과 사진 증빙을 연결할 때 왜 source 조정을 MERGED로 만드는가?
11. CNN의 네 sigmoid 출력은 softmax와 어떻게 다른가?
12. 합성 기울기 F1=1.0으로 실제 촬영 성능을 확정할 수 없는 이유는?

이 질문에 답할 수 있으면 이번 스프린트의 데이터 계약, 핵심 함수, 화면 처리, 비교평가의 주요 판단을 연결해 이해한 것이다.

## 35. 코드·보고서를 읽으며 원인을 좁히는 방법

금액이 틀리면 원본 사진→raw OCR 글자→text_boxes→KIE 후보·review_reasons→money_sources→현재 저장값 순서로 비교한다. OCR 글자 자체가 틀린 것과 올바른 숫자를 다른 라벨에 붙인 것은 개선 방법이 다르다.

품목이 섞이면 헤더 anchors, 행 y 그룹, pending 이름, footer 종료, assigned 열을 살펴본다. 수량 1로 임시 채워서 통과시키는 것은 원인을 고치는 방법이 아니다.

확정이 409이면 현재 Receipt revision과 화면 base_revision, confirmed 상태, 검사한 금액 상태를 먼저 본다. 거래 병합 409이면 거래 버전뿐 아니라 이동하는 모든 Receipt와 연결 조정거래 버전도 확인한다.

모델 실험 결과는 split manifest와 사진 SHA, real_labels, synthetic_reference를 먼저 확인한다. 실제 정답이 없는 예측을 성능 지표로 읽지 않는다. 정답 검증과 분포 확대 없이 높은 합성 점수만 보고 앱 품질 게이트를 바꾸지 않는다.


## 36. 최신 main 통합

사업자 검증·회원가입·Docker Compose·health·CI의 기존 main 구현을 보존했다. Alembic 015d7b1f7bdb와 20261005a5를 20261005a6 merge revision으로 연결해 기존 이력을 재작성하지 않았다. 두 출발 revision에서의 upgrade와 데이터 보존을 테스트한다. 문서의 Baseline 수치는 저장된 로컬 평가 결과이며 통합 시 새 OCR이나 학습을 수행하지 않았다.

## 부록. 현재 코드 선언 색인

각 파일의 클래스와 최상위 함수 선언이다. 링크는 저장소 기준 상대 경로이며 자격증명·로컬 사용자 경로를 포함하지 않는다.

### app/receipts/document.py

- [Region](../app/receipts/document.py#L8)
- [Evidence](../app/receipts/document.py#L15)
- [StructuredItem](../app/receipts/document.py#L23)
- [Discount](../app/receipts/document.py#L41)
- [DocumentFacts](../app/receipts/document.py#L52)
- [complete_item](../app/receipts/document.py#L125)
- [evidence_validation](../app/receipts/document.py#L145)

### app/receipts/evaluation.py

- [printed_targets](../app/receipts/evaluation.py#L22)
- [normalize](../app/receipts/evaluation.py#L31)
- [score](../app/receipts/evaluation.py#L39)
- [metrics](../app/receipts/evaluation.py#L48)
- [evaluate_record](../app/receipts/evaluation.py#L56)
- [run](../app/receipts/evaluation.py#L97)

### app/receipts/fingerprints.py

- [image_fingerprints](../app/receipts/fingerprints.py#L9)
- [backfill_image_fingerprints](../app/receipts/fingerprints.py#L21)

### app/receipts/kie.py

- [TextBox](../app/receipts/kie.py#L27)
- [boxes_from_fields](../app/receipts/kie.py#L45)
- [boxes_as_dicts](../app/receipts/kie.py#L60)
- [fill_from_boxes](../app/receipts/kie.py#L75)
- [_money_evidence](../app/receipts/kie.py#L160)
- [extract_line_items](../app/receipts/kie.py#L185)
- [_financial_label](../app/receipts/kie.py#L348)
- [financial_from_fields](../app/receipts/kie.py#L354)
- [_order_with_explicit_total](../app/receipts/kie.py#L375)
- [_read_financial_amount](../app/receipts/kie.py#L380)
- [_financial_values](../app/receipts/kie.py#L385)
- [_separate_order_subtotal](../app/receipts/kie.py#L403)
- [_is_phone_or_id](../app/receipts/kie.py#L415)
- [parse_amount](../app/receipts/kie.py#L424)
- [parse_business_number](../app/receipts/kie.py#L440)
- [parse_date](../app/receipts/kie.py#L449)
- [_box_from_poly](../app/receipts/kie.py#L461)
- [_amount_near_label](../app/receipts/kie.py#L483)
- [_top_vendor](../app/receipts/kie.py#L517)

### app/receipts/metadata.py

- [extract_metadata](../app/receipts/metadata.py#L6)

### app/receipts/models.py

- [Receipt](../app/receipts/models.py#L9)
- [Transaction](../app/receipts/models.py#L47)
- [LineItem](../app/receipts/models.py#L58)
- [ReconciliationIssue](../app/receipts/models.py#L66)

### app/receipts/money.py

- [complete_money](../app/receipts/money.py#L15)
- [structured_money](../app/receipts/money.py#L51)
- [money_problem](../app/receipts/money.py#L55)
- [complete_unit_price](../app/receipts/money.py#L66)
- [unit_price_problem](../app/receipts/money.py#L80)

### app/receipts/ocr_client.py

- [PartialRead](../app/receipts/ocr_client.py#L24)
- [OcrResult](../app/receipts/ocr_client.py#L60)
- [_field_text](../app/receipts/ocr_client.py#L94)
- [_parse_amount](../app/receipts/ocr_client.py#L104)
- [_parse_business_number](../app/receipts/ocr_client.py#L120)
- [_item_texts](../app/receipts/ocr_client.py#L129)
- [_parse_date](../app/receipts/ocr_client.py#L140)
- [_parse_text_lines](../app/receipts/ocr_client.py#L152)
- [parse_response](../app/receipts/ocr_client.py#L208)
- [collect_partial](../app/receipts/ocr_client.py#L341)
- [_result_from_filled](../app/receipts/ocr_client.py#L389)
- [_format_for_mime_type](../app/receipts/ocr_client.py#L414)
- [_extract_fallback](../app/receipts/ocr_client.py#L422)
- [extract_receipt](../app/receipts/ocr_client.py#L464)

### app/receipts/quality.py

- [QualityResult](../app/receipts/quality.py#L10)
- [inspect_receipt_image](../app/receipts/quality.py#L15)
- [_content_touches_all_edges](../app/receipts/quality.py#L44)

### app/receipts/quality_experiment.py

- [attach_visual_candidates](../app/receipts/quality_experiment.py#L28)
- [metric](../app/receipts/quality_experiment.py#L60)
- [tensor](../app/receipts/quality_experiment.py#L76)
- [induce](../app/receipts/quality_experiment.py#L82)
- [rule](../app/receipts/quality_experiment.py#L99)
- [rule_bytes](../app/receipts/quality_experiment.py#L105)
- [decode_tensor](../app/receipts/quality_experiment.py#L110)
- [SmallCNN](../app/receipts/quality_experiment.py#L115)
- [probabilities](../app/receipts/quality_experiment.py#L127)
- [train](../app/receipts/quality_experiment.py#L133)
- [thresholds](../app/receipts/quality_experiment.py#L154)
- [run](../app/receipts/quality_experiment.py#L166)

### app/receipts/router.py

- [upload_receipt](../app/receipts/router.py#L24)
- [list_receipts](../app/receipts/router.py#L37)
- [list_confirmed_receipts](../app/receipts/router.py#L45)
- [update_ocr](../app/receipts/router.py#L53)
- [confirm_receipt](../app/receipts/router.py#L63)
- [get_receipt_image](../app/receipts/router.py#L73)
- [get_receipt](../app/receipts/router.py#L83)

### app/receipts/schemas.py

- [ItemAmountIn](../app/receipts/schemas.py#L14)
- [ItemAmountOut](../app/receipts/schemas.py#L21)
- [ReceiptOut](../app/receipts/schemas.py#L30)
- [_parse_items](../app/receipts/schemas.py#L89)
- [ReceiptSummary](../app/receipts/schemas.py#L105)
- [ReceiptOcrUpdate](../app/receipts/schemas.py#L130)
- [ReceiptConfirmIn](../app/receipts/schemas.py#L171)

### app/receipts/service.py

- [detect_image_type](../app/receipts/service.py#L27)
- [_decode_image](../app/receipts/service.py#L35)
- [validate_image](../app/receipts/service.py#L82)
- [_delete_after_failure](../app/receipts/service.py#L105)
- [_rollback_best_effort](../app/receipts/service.py#L113)
- [_ocr_is_complete](../app/receipts/service.py#L121)
- [upload_receipt](../app/receipts/service.py#L131)
- [_ocr_snapshot](../app/receipts/service.py#L243)
- [_persist_receipt](../app/receipts/service.py#L263)
- [list_receipts](../app/receipts/service.py#L296)
- [get_receipt](../app/receipts/service.py#L305)
- [get_receipt_image](../app/receipts/service.py#L312)
- [_owned_receipt](../app/receipts/service.py#L320)
- [_reject_negative_money](../app/receipts/service.py#L330)
- [_manual_states](../app/receipts/service.py#L349)
- [_edited_document](../app/receipts/service.py#L361)
- [_save_line_items](../app/receipts/service.py#L381)
- [_sync_legacy_items](../app/receipts/service.py#L439)
- [update_ocr](../app/receipts/service.py#L456)
- [confirm_receipt](../app/receipts/service.py#L612)
- [list_confirmed_receipts](../app/receipts/service.py#L695)
- [_commit_receipt](../app/receipts/service.py#L704)

### app/receipts/storage.py

- [StoredFile](../app/receipts/storage.py#L14)
- [FileStorage](../app/receipts/storage.py#L20)
- [LocalFileStorage](../app/receipts/storage.py#L29)

### app/receipts/transactions.py

- [owned_transaction](../app/receipts/transactions.py#L23)
- [transaction_receipts](../app/receipts/transactions.py#L30)
- [create_from_receipt](../app/receipts/transactions.py#L34)
- [transaction_out](../app/receipts/transactions.py#L54)
- [list_transactions](../app/receipts/transactions.py#L75)
- [get_transaction](../app/receipts/transactions.py#L81)
- [get_evidence](../app/receipts/transactions.py#L86)
- [validate_evidence](../app/receipts/transactions.py#L92)
- [get_items](../app/receipts/transactions.py#L99)
- [ItemUsageIn](../app/receipts/transactions.py#L105)
- [lock_revision](../app/receipts/transactions.py#L112)
- [update_usage](../app/receipts/transactions.py#L121)
- [AdjustmentIn](../app/receipts/transactions.py#L139)
- [create_adjustment](../app/receipts/transactions.py#L166)
- [OriginalLinkIn](../app/receipts/transactions.py#L187)
- [link_original](../app/receipts/transactions.py#L195)
- [duplicate_reason](../app/receipts/transactions.py#L233)
- [find_duplicates](../app/receipts/transactions.py#L247)
- [get_issues](../app/receipts/transactions.py#L277)
- [ResolveIn](../app/receipts/transactions.py#L288)
- [merge_transactions](../app/receipts/transactions.py#L296)
- [resolve_issue](../app/receipts/transactions.py#L333)
- [EvidenceLinkIn](../app/receipts/transactions.py#L357)
- [link_adjustment_evidence](../app/receipts/transactions.py#L368)
- [link_evidence](../app/receipts/transactions.py#L419)
