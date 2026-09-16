# TAX-AI Backend — 전체 코드 명세 문서

> 본 문서는 프로젝트 내 **모든 요소**(모듈 · 컨트롤러 · 서비스 · 엔티티 · 리포지토리 · 클래스 · 인터페이스 · 타입 · 멤버 · 메서드 · 생성자 파라미터 · 데코레이터)를 빠짐없이 기록한다. 각 요소에는 그 의미와 역할을 함께 명시한다.
>
> 스택: NestJS 11 · TypeScript 5.7 · TypeORM 0.3 · PostgreSQL 16 (pgvector) · OpenAI GPT-4o · AWS S3 · Naver CLOVA OCR
> 현재 브랜치: main

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [디렉터리 구조](#2-디렉터리-구조)
3. [의존성](#3-의존성)
4. [환경 변수](#4-환경-변수)
5. [부트스트랩 & 루트 구성](#5-부트스트랩--루트-구성)
6. [공통 컴포넌트](#6-공통-컴포넌트)
7. [데이터베이스 엔티티 (전체 컬럼 명세)](#7-데이터베이스-엔티티-전체-컬럼-명세)
8. [모듈별 상세 명세](#8-모듈별-상세-명세)
   - [8.1 Auth](#81-auth-module)
   - [8.2 Users (엔티티 전용)](#82-users-엔티티-전용)
   - [8.3 Receipts](#83-receipts-module)
   - [8.4 OCR (내부 서비스)](#84-ocr-module-내부-서비스)
   - [8.5 S3 (내부 서비스)](#85-s3-module-내부-서비스)
   - [8.6 Validation](#86-validation-module)
   - [8.7 RAG](#87-rag-module)
   - [8.8 Deduction](#88-deduction-module)
   - [8.9 Reports](#89-reports-module)
9. [전체 API 엔드포인트 요약](#9-전체-api-엔드포인트-요약)
10. [인증 흐름](#10-인증-흐름)
11. [인프라 구성](#11-인프라-구성)
12. [코드와 기존 문서 간 차이 메모](#12-코드와-기존-문서-간-차이-메모)

---

## 1. 프로젝트 개요

소상공인을 위한 부가가치세(VAT) AI 세무 보조 백엔드. 핵심 파이프라인:

```
영수증 이미지 업로드 → Naver CLOVA OCR → 국세청(NTS) 사업자 진위 검증
   → LLM + RAG 매입세액공제 판단 → 부가세 신고서(PDF) 생성
```

| 항목 | 값 |
|---|---|
| 프레임워크 | NestJS 11 |
| 언어 | TypeScript 5.7 |
| ORM | TypeORM 0.3 |
| 데이터베이스 | PostgreSQL 16 + pgvector |
| LLM | OpenAI GPT-4o (`OPENAI_MODEL`, 기본 `gpt-4o`) |
| 임베딩 | OpenAI `text-embedding-3-small` (1536차원) |
| OCR | Naver CLOVA OCR Custom API (V2) |
| 파일 스토리지 | AWS S3 |
| 인증 | JWT(Bearer) + bcrypt + 휴대폰 OTP 본인인증 |
| PDF 생성 | pdfkit (CommonJS require) |
| 컨테이너 | Docker multi-stage build + Docker Compose |
| 리버스 프록시 | Nginx (rate limit, 120s timeout) |

기능 도메인은 9개 NestJS 모듈로 구성된다: `Auth`, `Receipts`, `Ocr`, `S3`, `Validation`, `Rag`, `Deduction`, `Reports`, 그리고 루트 `AppModule`. `Users`는 엔티티만 존재하는 도메인이다(별도 모듈 없음).

---

## 2. 디렉터리 구조

```
vat-ai-backend/
├── src/
│   ├── main.ts                                   # 부트스트랩 (NestFactory + Swagger)
│   ├── app.module.ts                             # 루트 모듈
│   ├── app.controller.ts                         # GET / 헬스/헬로 엔드포인트
│   ├── app.controller.spec.ts                    # AppController 단위 테스트
│   ├── app.service.ts                            # getHello() 제공
│   ├── database/
│   │   └── data-source.ts                         # TypeORM DataSource 설정 (CLI + 런타임 공용)
│   ├── common/
│   │   └── decorators/
│   │       └── current-user.decorator.ts          # @CurrentUser() 파라미터 데코레이터
│   ├── users/
│   │   └── entities/user.entity.ts                # User 엔티티 (모듈 없음)
│   ├── auth/
│   │   ├── auth.module.ts
│   │   ├── auth.controller.ts
│   │   ├── auth.service.ts
│   │   ├── jwt-user.interface.ts                  # JwtUser 인터페이스
│   │   ├── dto/auth.dto.ts                         # SendOtp/VerifyOtp/Register/Login DTO
│   │   ├── dto/payload.dto.ts                      # JWT Payload 클래스
│   │   ├── guards/jwt-auth.guard.ts                # JwtAuthGuard
│   │   └── strategies/jwt.strategy.ts             # JwtStrategy (passport-jwt)
│   ├── receipts/
│   │   ├── receipts.module.ts
│   │   ├── receipts.controller.ts
│   │   ├── receipts.service.ts
│   │   ├── dto/receipt.dto.ts                      # ManualItem/ManualReceipt/ConfirmReceipt DTO
│   │   └── entities/{receipt,item}.entity.ts
│   ├── ocr/
│   │   ├── ocr.module.ts
│   │   ├── ocr.service.ts                          # CLOVA OCR 호출 + 필드 추출
│   │   ├── dto/ocr-field.dto.ts                    # OcrField
│   │   ├── dto/ocr-result.dto.ts                   # OcrExtractedData
│   │   └── entities/ocr-result.entity.ts
│   ├── s3/
│   │   ├── s3.module.ts
│   │   └── s3.service.ts
│   ├── validation/
│   │   ├── validation.module.ts
│   │   ├── validation.controller.ts
│   │   ├── validation.service.ts
│   │   ├── dto/validation.dto.ts                   # ValidateBusinessDto
│   │   └── entities/validation.entity.ts
│   ├── rag/
│   │   ├── rag.module.ts
│   │   ├── rag.controller.ts
│   │   ├── rag.service.ts
│   │   ├── dto/rag-query.dto.ts                    # EmbedLawDocument/SearchRag/TaxQuery DTO
│   │   ├── entities/law-embedding.entity.ts
│   │   ├── guards/admin.guard.ts                   # AdminGuard (X-Admin-Key)
│   │   └── types/vector-column.ts                 # VectorColumn() 데코레이터
│   ├── deduction/
│   │   ├── deduction.module.ts
│   │   ├── deduction.controller.ts
│   │   ├── deduction.service.ts
│   │   └── entities/deduction.entity.ts
│   └── reports/
│       ├── reports.module.ts
│       ├── reports.controller.ts
│       ├── reports.service.ts                      # 신고서 집계 + pdfkit PDF 생성
│       ├── dto/report.dto.ts                       # GenerateReport/ConfirmReport DTO
│       └── entities/report.entity.ts               # Report + SupplierGroup 인터페이스
├── test/                                          # E2E 테스트
├── Dockerfile                                     # multi-stage build
├── docker-compose.yml                             # app + db(pgvector) + nginx
├── nginx.conf
├── .env.example
├── package.json
└── tsconfig.json
```

---

## 3. 의존성

### Runtime dependencies (`package.json`)

| 패키지 | 버전 | 용도 |
|---|---|---|
| `@nestjs/common`, `@nestjs/core` | ^11 | NestJS 핵심 |
| `@nestjs/platform-express` | ^11 | Express 어댑터 + `FileInterceptor`/`MulterModule` |
| `@nestjs/config` | ^4 | 환경 변수 (`ConfigModule`/`ConfigService`) |
| `@nestjs/jwt` | ^11 | JWT 서명/검증 (`JwtService`) |
| `@nestjs/passport` | ^11 | Passport 통합 (`PassportStrategy`, `AuthGuard`) |
| `@nestjs/swagger` | ^11 | Swagger UI (`/api`) |
| `@nestjs/typeorm` | ^11 | TypeORM 통합 (`InjectRepository`, `TypeOrmModule`) |
| `@aws-sdk/client-s3` | ^3 | S3 업로드 (`S3Client`, `PutObjectCommand`) |
| `openai` | ^6 | GPT-4o 채팅 완성 + 임베딩 |
| `passport`, `passport-jwt` | ^0.7 / ^4 | JWT 전략 |
| `bcrypt` | ^6 | 비밀번호 해시 |
| `pdfkit` | ^0.18 | PDF 생성 (CommonJS) |
| `typeorm` | ^0.3 | ORM |
| `pg` | ^8 | PostgreSQL 드라이버 |
| `axios` | ^1 | CLOVA OCR · NTS HTTP 클라이언트 |
| `multer` | ^2 | 파일 업로드 미들웨어 |
| `uuid` | ^14 | S3 키 / OTP 검증 토큰 / OCR requestId 생성 |
| `class-validator` | ^0.15 | DTO 유효성 검사 |
| `class-transformer` | ^0.5 | DTO 타입 변환 (`@Type`) |
| `reflect-metadata` | ^0.2 | 데코레이터 메타데이터 |
| `rxjs` | ^7 | NestJS 의존 |

### DevDependencies (발췌)

`@nestjs/cli`, `@nestjs/schematics`, `@nestjs/testing`, `typescript`, `ts-jest`, `jest`, `supertest`, `eslint`, `typescript-eslint`, `prettier`, `ts-node`, `tsconfig-paths`, `source-map-support`, `@types/*`.

### npm 스크립트

| 스크립트 | 명령 | 용도 |
|---|---|---|
| `build` | `nest build` | `dist/` 컴파일 |
| `start` | `nest start` | 일반 실행 |
| `start:dev` | `nest start --watch` | 핫 리로드 |
| `start:debug` | `nest start --debug --watch` | 디버그 + 워치 |
| `start:prod` | `node dist/main` | 컴파일 산출물 실행 |
| `format` | `prettier --write` | 포맷 |
| `lint` | `eslint --fix` | 린트 + 자동 수정 |
| `test` | `jest` | 단위 테스트 |
| `test:watch` / `test:cov` / `test:debug` | jest 변형 | 워치/커버리지/디버그 |
| `test:e2e` | `jest --config ./test/jest-e2e.json` | E2E |

---

## 4. 환경 변수

`.env.example`를 `.env`로 복사하여 사용한다(`.env`는 커밋 금지). 모든 변수는 `ConfigService.get<string>(...)`로 읽힌다. TypeORM CLI는 `data-source.ts`가 `dotenv.config()`로 직접 로드한다.

| 변수명 | 기본값(예시) | 읽는 위치 | 설명 |
|---|---|---|---|
| `PORT` | `3000` | `main.ts` | 앱 리슨 포트 (`process.env.PORT ?? 3000`) |
| `NODE_ENV` | `production` | `data-source.ts` | `synchronize`/`logging` 분기에 사용 |
| `DB_HOST` | `db` | `data-source.ts` | PostgreSQL 호스트 (Docker: `db`) |
| `DB_PORT` | `5432` | `data-source.ts` | 포트 (`parseInt`) |
| `DB_USER` | `taxai_user` | `data-source.ts` | DB 사용자 |
| `DB_PASS` | *(필수)* | `data-source.ts` | DB 비밀번호 |
| `DB_NAME` | `taxai` | `data-source.ts` | DB 이름 |
| `AWS_REGION` | `ap-northeast-2` | `S3Service` | S3 리전 (URL 구성 + 클라이언트) |
| `AWS_ACCESS_KEY_ID` | *(필수)* | `S3Service` | IAM 액세스 키 |
| `AWS_SECRET_ACCESS_KEY` | *(필수)* | `S3Service` | IAM 시크릿 키 |
| `AWS_S3_BUCKET` | `taxai-receipts` | `S3Service` | 버킷명 |
| `NAVER_OCR_API_URL` | *(필수)* | `OcrService` | CLOVA OCR Custom API URL |
| `NAVER_OCR_SECRET_KEY` | *(필수)* | `OcrService` | `X-OCR-SECRET` 헤더값 |
| `OPENAI_API_KEY` | *(필수)* | `RagService`, `DeductionService` | OpenAI 키 |
| `OPENAI_MODEL` | `gpt-4o` | `RagService`, `DeductionService` | 채팅 완성 모델 |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | `RagService` | 임베딩 모델 |
| `NTS_API_KEY` | *(필수)* | `ValidationService` | 국세청 API `serviceKey` 파라미터 |
| `NTS_API_URL` | `https://api.odcloud.kr/api/nts-businessman/v1` | `ValidationService` | 국세청 API Base URL |
| `JWT_SECRET` | *(필수, 32자+ 권장)* | `AuthModule`, `JwtStrategy` | JWT 서명/검증 키 |
| `JWT_EXPIRES_IN` | `7d` | `AuthModule` | JWT 만료 시간 |
| `PDF_FONT_PATH` | *(선택, 비움)* | `ReportsService` | 한글 폰트 경로 (폴백: `assets/fonts/NanumGothic.ttf` → Helvetica) |
| `ADMIN_API_KEY` | *(코드에서 사용, `.env.example`에는 미기재)* | `AdminGuard` | `POST /rag/embed` 보호 키 (`X-Admin-Key` 헤더와 비교) |

---

## 5. 부트스트랩 & 루트 구성

### `main.ts` — `bootstrap()`

| 요소 | 내용 |
|---|---|
| `NestFactory.create(AppModule)` | 앱 인스턴스 생성 |
| `new DocumentBuilder().build()` | Swagger 문서 설정 (제목/설명 미설정 — 최소 구성) |
| `SwaggerModule.setup('api', app, documentFactory)` | `/api`에 Swagger UI 등록 |
| `app.listen(process.env.PORT ?? 3000)` | 서버 리슨 |
| `void bootstrap()` | 진입점 호출 (반환 Promise 무시) |

> 전역 `ValidationPipe`는 등록되어 있지 않다. DTO 검증 데코레이터(`class-validator`)는 라우트 핸들러에서 자동 검증되지 않으므로, 검증을 강제하려면 별도 `app.useGlobalPipes(new ValidationPipe())` 추가가 필요하다.

### `AppModule` (`app.module.ts`)

`@Module` 데코레이터 구성:

| 키 | 값 | 역할 |
|---|---|---|
| `imports` | `ConfigModule.forRoot({ isGlobal: true })` | 전역 환경 변수 모듈 |
| | `TypeOrmModule.forRoot(dataSourceOptions)` | 전역 DB 연결 |
| | `AuthModule`, `ReceiptsModule`, `ValidationModule`, `RagModule`, `DeductionModule`, `ReportsModule` | 기능 모듈 (Ocr/S3는 각 모듈이 내부 import) |
| `controllers` | `[AppController]` | 루트 컨트롤러 |
| `providers` | `[AppService]` | 루트 서비스 |

### `AppController` (`app.controller.ts`)

- `@Controller()` — prefix 없음 (루트 `/`).
- 생성자: `constructor(private readonly appService: AppService)` — `AppService` 주입.
- 메서드: `@Get() getHello(): string` → `this.appService.getHello()` 반환. 헬스/헬로 용도.

### `AppService` (`app.service.ts`)

- `@Injectable()`.
- 메서드: `getHello(): string` → 상수 문자열 `'Hello World!'` 반환.

### `app.controller.spec.ts`

`AppController.getHello()`가 `'Hello World!'`를 반환하는지 검증하는 Jest 단위 테스트(`Test.createTestingModule`).

### `data-source.ts` — TypeORM 설정

```typescript
dotenv.config();   // CLI 실행 시 .env 직접 로드 (ConfigModule 미사용 경로)

export const dataSourceOptions: DataSourceOptions = {
  type: 'postgres',
  host:     process.env.DB_HOST || 'localhost',
  port:     parseInt(process.env.DB_PORT || '5432'),
  username: process.env.DB_USER || 'postgres',
  password: process.env.DB_PASS || 'postgres',
  database: process.env.DB_NAME || 'taxai',
  entities:   ['dist/**/*.entity{.ts,.js}'],   // 컴파일 산출물 기준 글롭
  migrations: ['dist/migrations/*{.ts,.js}'],
  synchronize: process.env.NODE_ENV === 'synchronize',  // 리터럴 'synchronize'와 정확히 일치할 때만 true
  logging:     process.env.NODE_ENV === 'development',
};

const dataSource = new DataSource(dataSourceOptions);
export default dataSource;   // TypeORM CLI용 default export
```

- `dataSourceOptions`: named export — `AppModule`의 `TypeOrmModule.forRoot()`가 재사용.
- `dataSource` (default export): TypeORM CLI(마이그레이션 등) 진입점.
- **`synchronize`**: `NODE_ENV` 값이 정확히 문자열 `'synchronize'`일 때만 활성화된다. `development`/`test`/`production` 등에서는 비활성. 프로덕션 스키마는 마이그레이션으로 관리.
- **`logging`**: `NODE_ENV === 'development'`일 때만 SQL 로깅.

---

## 6. 공통 컴포넌트

### `CurrentUser` 파라미터 데코레이터 — `src/common/decorators/current-user.decorator.ts`

```typescript
export const CurrentUser = createParamDecorator(
  (_data: unknown, ctx: ExecutionContext) => {
    const request = ctx.switchToHttp().getRequest<{ user: JwtUser }>();
    return request.user;
  },
);
```

- `JwtStrategy.validate()`가 `req.user`에 주입한 `JwtUser` 객체를 컨트롤러 파라미터로 추출.
- 사용 형태: `@CurrentUser() user: JwtUser`. `Receipts`, `Validation`, `Deduction`, `Reports` 컨트롤러에서 사용.
- 첫 인자 `_data`는 사용하지 않음(전체 user 객체 반환).

### `JwtUser` 인터페이스 — `src/auth/jwt-user.interface.ts`

```typescript
export interface JwtUser {
  userId: string;   // User.id (UUID 문자열)
  email: string;
}
```

모든 JWT 보호 컨트롤러가 공유하는 사용자 식별 타입. `@CurrentUser()`의 반환 타입.

### `JwtAuthGuard` — `src/auth/guards/jwt-auth.guard.ts`

```typescript
@Injectable()
export class JwtAuthGuard extends AuthGuard('jwt') {}
```

- Passport `AuthGuard('jwt')`를 그대로 확장(추가 로직 없음). `JwtStrategy`를 전략으로 사용.
- `@UseGuards(JwtAuthGuard)`를 클래스/메서드에 적용하면 Bearer 토큰 검증 후 `req.user`가 주입된다.
- 적용 컨트롤러: `Receipts`(클래스), `Validation`(클래스), `Deduction`(클래스), `Reports`(클래스), `Rag`(`search`/`query` 메서드 단위).

### `AdminGuard` — `src/rag/guards/admin.guard.ts`

```typescript
@Injectable()
export class AdminGuard implements CanActivate {
  constructor(private configService: ConfigService) {}

  canActivate(context: ExecutionContext): boolean {
    const request = context.switchToHttp().getRequest<Request>();
    const adminKey = request.headers['x-admin-key'];
    const expectedKey = this.configService.get<string>('ADMIN_API_KEY');
    if (!expectedKey || adminKey !== expectedKey) {
      throw new UnauthorizedException('Admin access required');
    }
    return true;
  }
}
```

- 생성자 파라미터 `configService: ConfigService` — 환경 변수 접근.
- `canActivate`: 요청 헤더 `x-admin-key`를 `ADMIN_API_KEY`와 비교. `ADMIN_API_KEY`가 미설정이면(`!expectedKey`) 무조건 거부.
- 현재 `POST /rag/embed`에만 적용.

### `VectorColumn()` 프로퍼티 데코레이터 — `src/rag/types/vector-column.ts`

```typescript
export function VectorColumn(): PropertyDecorator {
  return Column({
    type: 'text',
    transformer: {
      to:   (value: number[] | null): string | null =>
              value ? `[${value.join(',')}]` : null,   // number[] → "[x,y,z]" 문자열
      from: (value: string | null): number[] | null =>
              value ? (JSON.parse(value) as number[]) : null,  // "[x,y,z]" → number[]
    },
  });
}
```

- pgvector 1536차원 임베딩을 위한 컬럼 데코레이터. TypeScript에서는 `number[]`, DB에는 `text`로 저장.
- 값 트랜스포머: 삽입 시 배열을 `"[...]"` 문자열로, 읽기 시 `JSON.parse`로 역변환.
- 실제 유사도 검색(`<=>`)은 ORM이 아닌 `DataSource.query()` raw SQL에서 `$1::vector` 캐스팅으로 수행.
- pgvector 확장(`CREATE EXTENSION IF NOT EXISTS vector`)이 DB에 필요하며, 컬럼 타입은 마이그레이션(`1747353600000-VectorEmbeddingColumnType`)으로 관리한다(코드 주석 기준).
- 현재 `LawEmbedding.embedding`에만 적용.

> ⚠️ 주석에는 `synchronize: false`로 동기화 제외한다고 적혀 있으나, **실제 `Column({...})` 옵션에는 `synchronize: false`가 포함되어 있지 않다**(현재 코드 기준). 동기화가 켜진 환경에서 의도와 다르게 동작할 수 있다 — [§12](#12-코드와-기존-문서-간-차이-메모) 참조.

---

## 7. 데이터베이스 엔티티 (전체 컬럼 명세)

TypeORM `synchronize`는 `NODE_ENV === 'synchronize'`일 때만 활성화된다(§5). 모든 엔티티는 `dist/**/*.entity.js` 글롭으로 로드된다.

### 7.1 `User` — `users` 테이블

| 컬럼 | 데코레이터 | TS 타입 | 의미 |
|---|---|---|---|
| `id` | `@PrimaryGeneratedColumn('uuid')` | `string` | UUID v4 PK. JWT `sub` 클레임 = 이 값 |
| `email` | `@Column({ unique: true })` | `string` | 로그인 이메일 (유니크) |
| `password` | `@Column()` | `string` | bcrypt(rounds=10) 해시 |
| `store_name` | `@Column({ nullable: true })` | `string` | 상호명 |
| `business_number` | `@Column({ nullable: true })` | `string` | 사업자등록번호 |
| `phone` | `@Column({ nullable: true })` | `string` | 본인인증 완료 휴대폰 번호 |
| `created_at` | `@CreateDateColumn()` | `Date` | 생성 시각 |

### 7.2 `Receipt` — `receipts` 테이블

| 컬럼 | 데코레이터 | TS 타입 | 의미 |
|---|---|---|---|
| `id` | `@PrimaryGeneratedColumn()` | `number` | 자동 증가 PK |
| `user` | `@ManyToOne(() => User)` + `@JoinColumn({ name: 'user_id' })` | `User` | 소유 사용자 관계 |
| `user_id` | `@Column()` | `string` | FK → `users.id` (UUID) |
| `store_name` | `@Column({ nullable: true })` | `string` | 상호명 |
| `business_number` | `@Column({ nullable: true })` | `string` | 공급자 사업자번호 |
| `transaction_date` | `@Column({ type: 'date', nullable: true })` | `Date` | 거래일자 |
| `total_amount` | `@Column({ type: 'float', nullable: true })` | `number` | 공급가액 |
| `vat_amount` | `@Column({ type: 'float', nullable: true })` | `number` | 부가세액 |
| `s3_image_url` | `@Column({ nullable: true })` | `string` | 영수증 이미지 S3 URL |
| `raw_text` | `@Column({ type: 'text', nullable: true })` | `string` | OCR 원문 텍스트 |
| `purchase_purpose` | `@Column({ nullable: true })` | `string` | 구매 목적 (공제 판단 입력) |
| `items` | `@OneToMany(() => Item, (item) => item.receipt)` | `Item[]` | 품목 목록 |
| `ocr_results` | `@OneToMany(() => OcrResult, (ocr) => ocr.receipt)` | `OcrResult[]` | OCR 결과 (사실상 1:1) |
| `validations` | `@OneToMany(() => Validation, (v) => v.receipt)` | `Validation[]` | 사업자 검증 이력 |
| `deductions` | `@OneToMany(() => Deduction, (d) => d.receipt)` | `Deduction[]` | 공제 판단 이력 |
| `created_at` | `@CreateDateColumn()` | `Date` | 생성 시각 |

### 7.3 `Item` — `items` 테이블

| 컬럼 | 데코레이터 | TS 타입 | 의미 |
|---|---|---|---|
| `id` | `@PrimaryGeneratedColumn()` | `number` | PK |
| `receipt` | `@ManyToOne(() => Receipt)` + `@JoinColumn({ name: 'receipt_id' })` | `Receipt` | 소속 영수증 |
| `receipt_id` | `@Column()` | `number` | FK → `receipts.id` |
| `item_name` | `@Column()` | `string` | 품목명 |
| `price` | `@Column({ type: 'float' })` | `number` | 단가/금액 |
| `quantity` | `@Column({ type: 'int', default: 1 })` | `number` | 수량 (기본 1) |

### 7.4 `OcrResult` — `ocr_results` 테이블

| 컬럼 | 데코레이터 | TS 타입 | 의미 |
|---|---|---|---|
| `id` | `@PrimaryGeneratedColumn()` | `number` | PK |
| `receipt` | `@OneToOne(() => Receipt)` + `@JoinColumn({ name: 'receipt_id' })` | `Receipt` | 1:1 영수증 관계 |
| `receipt_id` | `@Column()` | `number` | FK → `receipts.id` |
| `extracted_json` | `@Column({ type: 'jsonb' })` | `object` | OCR 추출 원본 JSON (수기 입력 시 `{}`) |
| `confidence_score` | `@Column({ type: 'float', default: 0 })` | `number` | 평균 신뢰도 0~1 (수기 입력 시 1.0) |
| `is_user_confirmed` | `@Column({ default: false })` | `boolean` | 사용자 확정 여부 |
| `confirmed_at` | `@Column({ nullable: true })` | `Date` | 확정 시각 |
| `created_at` | `@CreateDateColumn()` | `Date` | 생성 시각 |

### 7.5 `Validation` — `validations` 테이블

| 컬럼 | 데코레이터 | TS 타입 | 의미 |
|---|---|---|---|
| `id` | `@PrimaryGeneratedColumn()` | `number` | PK |
| `receipt` | `@ManyToOne(() => Receipt)` + `@JoinColumn({ name: 'receipt_id' })` | `Receipt` | 소속 영수증 |
| `receipt_id` | `@Column()` | `number` | FK → `receipts.id` |
| `is_valid` | `@Column()` | `boolean` | 유효 사업자 여부 (`b_stt_cd === '01'`) |
| `status` | `@Column({ nullable: true })` | `string` | 국세청 사업자 상태명 |
| `api_response` | `@Column({ type: 'text', nullable: true })` | `string` | 검증 결과 JSON 직렬화 문자열 |
| `created_at` | `@CreateDateColumn()` | `Date` | 생성 시각 |

### 7.6 `Deduction` — `deductions` 테이블

| 컬럼 | 데코레이터 | TS 타입 | 의미 |
|---|---|---|---|
| `id` | `@PrimaryGeneratedColumn()` | `number` | PK |
| `receipt` | `@ManyToOne(() => Receipt)` + `@JoinColumn({ name: 'receipt_id' })` | `Receipt` | 소속 영수증 |
| `receipt_id` | `@Column()` | `number` | FK → `receipts.id` |
| `is_deductible` | `@Column()` | `boolean` | 매입세액 공제 가능 여부 |
| `reason` | `@Column({ type: 'text', nullable: true })` | `string` | LLM 판단 근거(한국어) |
| `related_law` | `@Column({ nullable: true })` | `string` | 관련 법령 조문명 |
| `confidence_score` | `@Column({ type: 'float', default: 0 })` | `number` | LLM 신뢰도 0~1 |
| `applicable_rate` | `@Column({ type: 'float', nullable: true })` | `number` | 적용 공제율 |
| `deductible_amount` | `@Column({ type: 'float', nullable: true })` | `number` | 공제 가능 금액 |
| `created_at` | `@CreateDateColumn()` | `Date` | 생성 시각 |

### 7.7 `Report` — `reports` 테이블 (+ `SupplierGroup` 인터페이스)

```typescript
export interface SupplierGroup {
  business_number: string;      // 매입처 사업자번호
  store_name: string;           // 매입처 상호명
  total_supply_amount: number;  // 공급가액 합계
  total_vat: number;            // 공제 세액 합계
}
```

`SupplierGroup`은 매입처별 세금계산서 합계표 한 행을 나타내며 `Report.grouped_suppliers`(jsonb)에 저장된다.

| 컬럼 | 데코레이터 | TS 타입 | 의미 |
|---|---|---|---|
| `id` | `@PrimaryGeneratedColumn()` | `number` | PK |
| `user` | `@ManyToOne(() => User)` + `@JoinColumn({ name: 'user_id' })` | `User` | 소유 사용자 |
| `user_id` | `@Column()` | `string` | FK → `users.id` (UUID) |
| `period_start` | `@Column({ type: 'date' })` | `Date` | 신고 기간 시작 |
| `period_end` | `@Column({ type: 'date' })` | `Date` | 신고 기간 종료 |
| `report_type` | `@Column({ default: 'general' })` | `string` | `'general'`(일반과세자) \| `'simplified'`(간이과세자) |
| `is_user_confirmed` | `@Column({ default: false })` | `boolean` | 사용자 확정 여부 |
| `confirmed_at` | `@Column({ nullable: true })` | `Date` | 확정 시각 |
| `total_output_tax` | `@Column({ type: 'float' })` | `number` | 매출세액 (현재 항상 0) |
| `total_input_tax` | `@Column({ type: 'float' })` | `number` | 공제 매입세액 합계 |
| `final_tax` | `@Column({ type: 'float' })` | `number` | 납부(환급)세액 = output − input |
| `grouped_suppliers` | `@Column({ type: 'jsonb', nullable: true })` | `SupplierGroup[]` | 매입처별 합계표 |
| `pdf_url` | `@Column({ nullable: true })` | `string` | 생성된 PDF S3 URL |
| `created_at` | `@CreateDateColumn()` | `Date` | 생성 시각 |

### 7.8 `LawEmbedding` — `law_embeddings` 테이블

| 컬럼 | 데코레이터 | TS 타입 | 의미 |
|---|---|---|---|
| `id` | `@PrimaryGeneratedColumn()` | `number` | PK |
| `source` | `@Column()` | `string` | 법령명 (예: `부가가치세법`) |
| `content` | `@Column({ type: 'text' })` | `string` | 조문 내용 |
| `article` | `@Column({ type: 'text', nullable: true })` | `string` | 조문번호 |
| `embedding` | `@VectorColumn()` | `number[]` | 1536차원 임베딩 (DB: text, pgvector `<=>` 검색) |
| `created_at` | `@CreateDateColumn()` | `Date` | 생성 시각 |

---

## 8. 모듈별 상세 명세

각 모듈은 `@Module({ imports, controllers, providers, exports })` 구조를 따른다. 아래는 모듈 메타데이터, 컨트롤러(라우트별 데코레이터/파라미터), 서비스(생성자 주입 + 메서드 시그니처/역할 + 내부 타입), DTO(필드별 검증 데코레이터)를 전부 기술한다.

---

### 8.1 Auth Module

**경로**: `src/auth/` · **prefix**: `/auth` · **인증**: 전부 Public

#### 모듈 (`AuthModule`)

| 키 | 내용 |
|---|---|
| `imports` | `TypeOrmModule.forFeature([User])`, `PassportModule`, `JwtModule.registerAsync(...)`, `ValidationModule` |
| `JwtModule.registerAsync` | `useFactory`가 `ConfigService`에서 `JWT_SECRET`(없으면 `''`), `JWT_EXPIRES_IN`(없으면 `'7d'`)을 읽어 `{ secret, signOptions: { expiresIn } }` 반환. `inject: [ConfigService]` |
| `controllers` | `[AuthController]` |
| `providers` | `[AuthService, JwtStrategy]` |
| `exports` | `[AuthService]` (다른 모듈에서 재사용 가능하도록) |

#### DTO / 타입 (`dto/auth.dto.ts`, `dto/payload.dto.ts`, `jwt-user.interface.ts`)

```typescript
class SendOtpDto {
  @IsMobilePhone('ko-KR', {}, { message: '올바른 휴대폰 번호를 입력하세요.' })
  phone: string;
}

class VerifyOtpDto {
  @IsMobilePhone('ko-KR', {}, { message: '...' })   phone: string;
  @IsString() @MinLength(6) @MaxLength(6)            otp: string;   // 6자리 정확히
}

class RegisterDto {
  @IsEmail({}, { message: '...' })                   email: string;
  @IsString()
  @MinLength(8, { message: '...' })
  @Matches(/^(?=.*[a-zA-Z])(?=.*\d)/, { message: '...' })  password: string;  // 영문+숫자 필수
  @IsString()  store_name: string;
  @IsString()  business_number: string;
  @IsString()  phone_verified_token: string;         // verifyOtp 발급 토큰
}

class LoginDto {
  @IsEmail()   email: string;
  @IsString()  password: string;
}

// JWT 페이로드 (토큰 내부 클레임) — payload.dto.ts
class Payload {
  sub: string;    // User.id (UUID)
  email: string;
}
```

> `Payload`는 `class` (interface 아님) — `JwtStrategy.validate()`에서 `payload instanceof Payload` 타입 가드에 쓰인다.

#### `AuthService` 내부 타입 (인메모리 저장소)

```typescript
interface OtpEntry {
  otp: string;       // Math.floor(100000 + Math.random()*900000).toString()
  expiresAt: Date;   // Date.now() + 5*60*1000  (5분)
}
interface VerifiedTokenEntry {
  phone: string;     // 검증 완료 번호
  expiresAt: Date;   // Date.now() + 10*60*1000 (10분)
}
```

- `private readonly otpStore = new Map<string, OtpEntry>()` — phone → OTP 매핑.
- `private readonly verifiedTokenStore = new Map<string, VerifiedTokenEntry>()` — token → 검증정보 매핑.
- 단일 인스턴스 메모리 저장. 다중 인스턴스 배포 시 Redis 등으로 교체 필요.

#### `AuthService` 생성자 주입

| 파라미터 | 타입 | 역할 |
|---|---|---|
| `usersRepository` | `@InjectRepository(User) Repository<User>` | 사용자 CRUD |
| `jwtService` | `JwtService` | `access_token` 서명 |
| `validationService` | `ValidationService` | 회원가입 시 사업자 진위 확인 |

#### `AuthService` 메서드

| 메서드 | 시그니처 | 역할 |
|---|---|---|
| `sendOtp` | `(phone: string): Promise<{ message }>` | 6자리 OTP 생성 → `otpStore`에 TTL 5분 저장 → 콘솔 로그 출력(실서비스는 SMS 연동) |
| `verifyOtp` | `(phone, otp): Promise<{ phone_verified_token }>` | OTP 존재/만료/일치 검증 → 성공 시 `otpStore` 삭제 후 UUID 토큰(TTL 10분) 발급·저장 |
| `register` | `(dto: RegisterDto)` | ① 토큰 유효/만료 확인 ② 이메일 중복 확인 ③ NTS 사업자 진위 확인 ④ bcrypt(10) 해시 ⑤ 토큰의 phone으로 User 저장 ⑥ JWT 발급. 반환: `{ access_token, user: { id, email, store_name, business_number, phone } }` |
| `login` | `(dto: LoginDto)` | 이메일 조회 → bcrypt 비교 → JWT 발급. 반환: `{ access_token, user: { id, email, store_name, business_number } }` |

예외: 인증 실패 `UnauthorizedException`, 이메일 중복 `ConflictException`, 검증/만료/잘못된 입력 `BadRequestException`.

#### `JwtStrategy` (`strategies/jwt.strategy.ts`)

- `extends PassportStrategy(Strategy)` (passport-jwt).
- 생성자 파라미터: `configService: ConfigService`, `@InjectRepository(User) usersRepository: Repository<User>`.
- `super({...})` 옵션: `jwtFromRequest: ExtractJwt.fromAuthHeaderAsBearerToken()`, `secretOrKey: JWT_SECRET`, `ignoreExpiration: false`.
- `async validate(payload: unknown): Promise<JwtUser>` — `payload instanceof Payload` 가드 통과 → `usersRepository`에서 `id = payload.sub` 사용자 재조회 → 없으면 `UnauthorizedException`, 있으면 `{ userId: user.id, email: user.email }` 반환 (= `req.user`).

#### API 엔드포인트

| Method | Path | Body | Response |
|---|---|---|---|
| `POST` | `/auth/phone/send-otp` | `SendOtpDto` | `{ message }` |
| `POST` | `/auth/phone/verify-otp` | `VerifyOtpDto` | `{ phone_verified_token }` |
| `POST` | `/auth/register` | `RegisterDto` | `{ access_token, user{...} }` |
| `POST` | `/auth/login` | `LoginDto` | `{ access_token, user{...} }` |

`AuthController` 생성자: `private readonly authService: AuthService`. 각 핸들러는 `@Body() dto`를 받아 서비스 메서드로 위임.

---

### 8.2 Users (엔티티 전용)

**경로**: `src/users/entities/user.entity.ts`

별도 모듈/컨트롤러/서비스가 없는 도메인. `User` 엔티티(§7.1)만 정의되며, `AuthModule`·`JwtStrategy`가 `TypeOrmModule.forFeature([User])`로 리포지토리를 주입받아 사용한다. `Receipt`/`Report`가 `@ManyToOne(() => User)`로 참조한다.

---

### 8.3 Receipts Module

**경로**: `src/receipts/` · **prefix**: `/receipts` · **인증**: 클래스 단위 `@UseGuards(JwtAuthGuard)`

#### 모듈 (`ReceiptsModule`)

| 키 | 내용 |
|---|---|
| `imports` | `TypeOrmModule.forFeature([Receipt, Item, OcrResult])`, `OcrModule`, `S3Module`, `MulterModule.register({...})` |
| `MulterModule` 옵션 | `limits.fileSize = 10MB`; `fileFilter`가 `image/jpeg`·`image/png`·`image/heic`만 허용(그 외 `new Error('Invalid file type')`) |
| `controllers` | `[ReceiptsController]` |
| `providers` | `[ReceiptsService]` |

#### DTO (`dto/receipt.dto.ts`)

```typescript
class ManualItemDto {                       // (모듈 비공개 — ManualReceiptDto 중첩용)
  @IsString()  item_name: string;
  @IsNumber()  price: number;
  @IsNumber()  quantity: number;
}

export class ManualReceiptDto {
  @IsOptional() @IsString()      store_name?: string;
  @IsOptional() @IsString()      business_number?: string;
  @IsOptional() @IsDateString()  transaction_date?: string;   // 'YYYY-MM-DD'
  @IsOptional() @IsNumber()      total_amount?: number;
  @IsOptional() @IsNumber()      vat_amount?: number;
  @IsOptional() @IsString()      purchase_purpose?: string;
  @IsOptional() @IsArray()
  @ValidateNested({ each: true })
  @Type(() => ManualItemDto)     items?: ManualItemDto[];
}

export class ConfirmReceiptDto {
  @IsBoolean()   confirmed: boolean;
  @IsOptional()  corrections?: {
    store_name?: string;
    total_amount?: number;
    items?: Array<{ item_name: string; price: number; quantity: number }>;
  };
}
```

#### `ReceiptsService` 생성자 주입

| 파라미터 | 타입 | 역할 |
|---|---|---|
| `receiptsRepository` | `Repository<Receipt>` | 영수증 CRUD |
| `itemsRepository` | `Repository<Item>` | 품목 CRUD |
| `ocrResultsRepository` | `Repository<OcrResult>` | OCR 결과 CRUD |
| `ocrService` | `OcrService` | CLOVA OCR 처리 |
| `s3Service` | `S3Service` | 이미지 S3 업로드 |

#### `ReceiptsService` 메서드

| 메서드 | 시그니처 | 역할 |
|---|---|---|
| `uploadReceipt` | `(userId: string, file: Express.Multer.File, purchasePurpose?: string)` | S3 업로드 → CLOVA OCR → Receipt+Item[]+OcrResult(`is_user_confirmed=false`) 저장. 실패 시 `HttpException(500)`. 반환 `{ receipt_id, s3_url, ocr_result, is_user_confirmed }` |
| `getUserReceipts` | `(userId: string)` | `items`, `ocr_results` 관계 포함, `created_at DESC` 정렬 후 평탄화 매핑. `ocr_result`는 `ocr_results[0]` |
| `getReceiptById` | `(receiptId: number, userId: string)` | `items, ocr_results, validations, deductions` 관계 포함 상세. 없으면 404 |
| `confirmReceipt` | `(receiptId, userId, confirmDto: ConfirmReceiptDto)` | `corrections`로 store_name/total_amount/items 교체(items는 delete 후 재삽입) → `OcrResult.is_user_confirmed` 및 `confirmed_at` 갱신. 반환 `{ receipt_id, confirmed, message }` |
| `createManualReceipt` | `(userId, dto: ManualReceiptDto)` | OCR 없이 입력값으로 Receipt+Item[] 저장, OcrResult를 `extracted_json={}`, `confidence_score=1.0`, `is_user_confirmed=true`로 즉시 확정. 반환 `{ receipt_id, is_manual, is_user_confirmed }` |
| `reUploadReceiptImage` | `(receiptId, userId, file)` | 새 이미지 S3 업로드 → OCR 재실행 → Receipt 필드 갱신(`??` 폴백) → items 전체 교체 → OcrResult 갱신/생성(`is_user_confirmed=false`, `confirmed_at=null`). 반환 `{ receipt_id, s3_url, ocr_result, is_user_confirmed }` |

#### 컨트롤러 (`ReceiptsController`)

생성자: `private readonly receiptsService: ReceiptsService`. 클래스에 `@UseGuards(JwtAuthGuard)`.

| Method | Path | 핸들러 | 파라미터 데코레이터 |
|---|---|---|---|
| `POST` | `/receipts/upload` | `uploadReceipt` | `@UseInterceptors(FileInterceptor('file'))`, `@CurrentUser() user`, `@UploadedFile() file`, `@Body('purchase_purpose') purchasePurpose?` |
| `POST` | `/receipts/manual` | `createManualReceipt` | `@CurrentUser() user`, `@Body() dto: ManualReceiptDto` |
| `GET` | `/receipts` | `getUserReceipts` | `@CurrentUser() user` |
| `GET` | `/receipts/:id` | `getReceiptById` | `@Param('id', ParseIntPipe) id`, `@CurrentUser() user` |
| `PATCH` | `/receipts/:id/confirm` | `confirmReceipt` | `@Param('id', ParseIntPipe) id`, `@CurrentUser() user`, `@Body() confirmDto` |
| `PATCH` | `/receipts/:id/image` | `reUploadReceiptImage` | `@UseInterceptors(FileInterceptor('file'))`, `@Param('id', ParseIntPipe) id`, `@CurrentUser() user`, `@UploadedFile() file` |

> 라우트 순서: `GET /receipts/:id`와 `POST /receipts/manual`은 HTTP 메서드가 달라 충돌하지 않고, `:id/confirm`·`:id/image`는 세그먼트가 달라 순서 무관.

---

### 8.4 OCR Module (내부 서비스)

**경로**: `src/ocr/` · **외부 엔드포인트 없음** — `ReceiptsModule`이 import하여 주입.

#### 모듈 (`OcrModule`)

- `imports`: `ConfigModule`, `TypeOrmModule.forFeature([OcrResult])`
- `providers`/`exports`: `[OcrService]`

#### 타입

```typescript
// dto/ocr-field.dto.ts — CLOVA 응답 fields[] 원소
class OcrField {
  name: string;
  inferText?: string;
  inferConfidence?: number;
}

// ocr.service.ts 내부 — CLOVA 응답 전체 구조
interface NaverOcrResponse {
  images: Array<{ fields: Array<{ name: string; inferText: string; inferConfidence: number }> }>;
}

// dto/ocr-result.dto.ts — 추출 결과 표준 형태
class OcrExtractedData {
  store_name: string;
  business_number: string;
  transaction_date: string;   // 'YYYY-MM-DD' 형태 기대
  total_amount: number;       // 공급가액
  vat_amount: number;         // 세액
  items: Array<{ item_name: string; price: number; quantity: number }>;
  confidence_score: number;   // 0~1 (필드 평균)
  raw_text: string;           // 전체 inferText '\n' join
}
```

#### `OcrService`

생성자 파라미터: `configService: ConfigService`. 인스턴스 필드 `axiosInstance`(공통 `X-OCR-SECRET` 헤더), `apiUrl`(`NAVER_OCR_API_URL`), `secretKey`(`NAVER_OCR_SECRET_KEY`).

| 메서드 | 접근 | 시그니처 | 역할 |
|---|---|---|---|
| `processReceipt` | public | `(imageBuffer: Buffer, mimeType): Promise<OcrExtractedData>` | Base64 인코딩 → `{ version:'V2', requestId: uuid4(), timestamp, images:[{format, name:'receipt', data}] }` POST → `extractData`. Axios 오류 시 `HttpException(400)`, 그 외 `500` |
| `extractData` | private | `(response: NaverOcrResponse): OcrExtractedData` | `images[0].fields`에서 상호명/사업자등록번호/작성일자/공급가액/세액/품목 매핑 + 신뢰도/raw_text |
| `extractField` | private | `(fields, fieldName): string` | `fields.find(f => f.name === fieldName)?.inferText ?? ''` |
| `extractNumberField` | private | `(fields, fieldName): number` | `extractField` 결과에서 `[^0-9.-]` 제거 후 `parseFloat`(없으면 0) |
| `extractItems` | private | `(fields): Array<{item_name, price, quantity}>` | `name === '품목'` 필드를 공백 분리: `parts[0]`=품목명, 마지막=가격, parts>2면 `parts[1]`=수량(기본 1) |
| `calculateConfidence` | private | `(fields): number` | 전체 `inferConfidence` 평균(필드 0개면 0) |
| `getFormat` | private | `(mimeType): string` | MIME → CLOVA format (`image/jpeg`→`jpg`, `png`, `heic`, 기본 `jpg`) |

추출 대상 한글 필드명: `상호명`, `사업자등록번호`, `작성일자`, `공급가액`, `세액`, `품목`.

---

### 8.5 S3 Module (내부 서비스)

**경로**: `src/s3/` · **외부 엔드포인트 없음** — `ReceiptsModule`, `ReportsModule`이 주입.

#### 모듈 (`S3Module`)

- `imports`: `ConfigModule`
- `providers`/`exports`: `[S3Service]`

#### `S3Service`

생성자 파라미터: `configService: ConfigService`. 필드: `s3Client`(`new S3Client({ region, credentials })`), `bucket`(`AWS_S3_BUCKET`), `region`(`AWS_REGION`).

| 메서드 | 접근 | 시그니처 | 역할 / S3 키 |
|---|---|---|---|
| `upload` | public | `(buffer: Buffer, key: string, contentType: string): Promise<string>` | `PutObjectCommand` 전송 후 `https://{bucket}.s3.{region}.amazonaws.com/{key}` 반환 |
| `uploadReceiptImage` | public | `(buffer, contentType): Promise<string>` | 키 `receipts/{uuid}.{ext}`로 `upload` 호출 |
| `uploadReportPdf` | public | `(buffer, reportId: number): Promise<string>` | 키 `reports/report_{id}.pdf`, contentType `application/pdf` |
| `getExtension` | private | `(contentType): string` | MIME → 확장자 (`jpg`/`png`/`heic`, 기본 `jpg`) |

---

### 8.6 Validation Module

**경로**: `src/validation/` · **prefix**: `/validation` · **인증**: 클래스 단위 `@UseGuards(JwtAuthGuard)`

#### 모듈 (`ValidationModule`)

- `imports`: `TypeOrmModule.forFeature([Validation, Receipt])`, `ConfigModule`
- `controllers`: `[ValidationController]`
- `providers`/`exports`: `[ValidationService]` (export → `AuthModule`이 회원가입 검증에 사용)

#### DTO / 내부 타입

```typescript
// dto/validation.dto.ts
class ValidateBusinessDto {
  @IsString()  business_number: string;   // 하이픈 포함/제외 모두 허용
}

// validation.service.ts 내부 — 국세청 API 응답
interface NtsBusinessItem {
  b_no: string;        // 사업자등록번호(하이픈 제거)
  b_stt: string;       // 상태명 (예: '계속사업자')
  b_stt_cd: string;    // 상태 코드 ('01' = 계속사업자 → is_valid)
  tax_type: string;    // 과세 유형
  tax_type_cd: string;
  end_dt: string;      // 폐업일
  utcc_yn: string;     // 단위과세 전환 여부
}
interface NtsApiResponse {
  status_code: string;
  request_cnt: number;
  match_cnt: number;
  data: NtsBusinessItem[];
}
```

#### `ValidationService`

생성자: `configService: ConfigService`, `@InjectRepository(Validation) validationsRepository`, `@InjectRepository(Receipt) receiptsRepository`. 필드: `apiKey`(`NTS_API_KEY`), `apiUrl`(`NTS_API_URL`).

| 메서드 | 접근 | 시그니처 | 역할 |
|---|---|---|---|
| `normalizeBusinessNumber` | private | `(businessNumber): string` | 하이픈 제거 (`replace(/-/g,'')`) |
| `validateBusiness` | public | `(dto: ValidateBusinessDto)` | 정규화 → `POST {apiUrl}/status` (`body { b_no:[...] }`, `params { serviceKey }`) → `data[0]` 없으면 404 → `is_valid = b_stt_cd==='01'`. 반환 `{ is_valid, status, tax_type, business_number }` |
| `validateReceiptBusiness` | public | `(receiptId, userId)` | 영수증 조회(없으면 404, 사업자번호 없으면 400) → `validateBusiness` → Validation **upsert**(`api_response`=JSON 문자열). 반환 검증 결과 |
| `getValidationByReceipt` | public | `(receiptId, userId)` | 영수증·검증 조회(없으면 404) → `api_response` JSON 파싱하여 `{ id, receipt_id, is_valid, status, api_response, created_at }` 반환 |

#### 컨트롤러 (`ValidationController`)

생성자: `private readonly validationService`. 클래스에 `@UseGuards(JwtAuthGuard)`. (`Request`를 import하나 핸들러에서는 `@CurrentUser()` 사용.)

| Method | Path | 핸들러 | 파라미터 |
|---|---|---|---|
| `POST` | `/validation/business` | `validateBusiness` | `@Body() dto: ValidateBusinessDto` |
| `POST` | `/validation/receipt/:receipt_id` | `validateReceiptBusiness` | `@Param('receipt_id', ParseIntPipe)`, `@CurrentUser() user` |
| `GET` | `/validation/receipt/:receipt_id` | `getValidationByReceipt` | `@Param('receipt_id', ParseIntPipe)`, `@CurrentUser() user` |

---

### 8.7 RAG Module

**경로**: `src/rag/` · **prefix**: `/rag` · **인증**: 메서드 단위(`embed`=AdminGuard, `search`/`query`=JwtAuthGuard)

#### 모듈 (`RagModule`)

- `imports`: `TypeOrmModule.forFeature([LawEmbedding])`, `ConfigModule`
- `controllers`: `[RagController]`
- `providers`: `[RagService, AdminGuard]`
- `exports`: `[RagService]` (→ `DeductionModule`이 검색에 사용)

#### DTO (`dto/rag-query.dto.ts`)

```typescript
export class EmbedLawDocumentDto {
  @IsString()              content: string;   // 조문 내용
  @IsString()              source: string;    // 법령명
  @IsString() @IsOptional()  article?: string;  // 조문번호
}

export class SearchRagDto {
  @IsString()  query: string;
  @IsOptional() @IsInt() @Min(1) @Max(20) @Type(() => Number)
  top_k?: number;            // 기본 5
}

export class TaxQueryDto {
  @IsString()  question: string;
  @IsOptional() @IsArray() @IsInt({ each: true }) @Type(() => Number)
  exclude_law_ids?: number[];  // 재탐색 시 제외할 법령 ID 목록
}
```

#### 내부 타입

```typescript
// rag.service.ts — raw SQL 결과 행
interface LawEmbeddingRow {
  id: number; source: string; content: string; article: string;
  created_at: Date; distance?: number;   // embedding <=> query_vector (코사인 거리)
}
```

#### `RagService`

생성자: `configService: ConfigService`, `dataSource: DataSource`(raw SQL용), `@InjectRepository(LawEmbedding) lawEmbeddingRepository`. 필드: `openai`(`new OpenAI({apiKey})`), `embeddingModel`(`EMBEDDING_MODEL`).

| 메서드 | 접근 | 시그니처 | 역할 |
|---|---|---|---|
| `getEmbedding` | private | `(text): Promise<number[]>` | `openai.embeddings.create({model, input})` → `data[0].embedding`. 실패 시 `HttpException(502/500)` |
| `embedLawDocument` | public | `(content, source, article): Promise<void>` | `getEmbedding(content)` → ORM `create` + `save` (VectorColumn 트랜스포머로 text 저장) |
| `searchRelevantLaws` | public | `(query, topK=5, excludeIds=[]): Promise<LawEmbedding[]>` | `getEmbedding(query)` → raw SQL: `(embedding <=> $1::vector) AS distance ... ORDER BY distance ASC LIMIT $2`. `excludeIds`는 `AND id NOT IN (...)`. 결과 행을 `LawEmbedding` 인스턴스로 매핑(embedding 필드 제외) |
| `answerTaxQuery` | public | `(question, excludeIds=[]): Promise<{ answer, relevant_laws, has_more }>` | `searchRelevantLaws(topK=5)` → 조문 컨텍스트 구성 → GPT(`OPENAI_MODEL`) **단일 user 메시지**로 답변 생성 → `SELECT COUNT(*)`로 `has_more = total > excludeIds.length + topK` 계산 |

#### 컨트롤러 (`RagController`)

생성자: `private readonly ragService`. 클래스 가드 없음 — 메서드별 지정.

| Method | Path | 가드 | 핸들러 / 동작 |
|---|---|---|---|
| `POST` | `/rag/embed` | `@UseGuards(AdminGuard)` | `embedLawDocument(dto.content, dto.source, dto.article ?? '')` → `{ message }` |
| `POST` | `/rag/search` | `@UseGuards(JwtAuthGuard)` | `searchRelevantLaws(dto.query, dto.top_k ?? 5)` → `LawEmbedding[]` |
| `POST` | `/rag/query` | `@UseGuards(JwtAuthGuard)` | `answerTaxQuery(dto.question, dto.exclude_law_ids ?? [])` → `{ answer, relevant_laws, has_more }` |

> **법령 재탐색**: `/rag/query` 응답의 `relevant_laws[].id`를 `exclude_law_ids`로 재요청하면 본 조문을 제외하고 새 조문을 검색. `has_more=false`면 더 없음.

---

### 8.8 Deduction Module

**경로**: `src/deduction/` · **prefix**: `/deduction` · **인증**: 클래스 단위 `@UseGuards(JwtAuthGuard)`

#### 모듈 (`DeductionModule`)

- `imports`: `TypeOrmModule.forFeature([Deduction, Receipt, Validation])`, `ConfigModule`, `RagModule`
- `controllers`: `[DeductionController]`
- `providers`/`exports`: `[DeductionService]`

#### 내부 타입 (LLM JSON 응답)

```typescript
interface LlmDeductionResult {
  is_deductible: boolean;
  confidence_score: number;     // 0~1
  reason: string;               // 한국어 근거 2~3문장
  related_law: string;          // 관련 조문명
  applicable_rate: number | null;
  deductible_amount: number;
}
```

#### `DeductionService`

생성자: `@InjectRepository(Deduction) deductionsRepository`, `@InjectRepository(Receipt) receiptsRepository`, `@InjectRepository(Validation) validationsRepository`, `ragService: RagService`, `configService: ConfigService`. 필드: `openai`, `model`(`OPENAI_MODEL`).

| 메서드 | 접근 | 시그니처 | 역할 |
|---|---|---|---|
| `analyzeDeduction` | public | `(receiptId, userId): Promise<Deduction>` | 영수증(+items) 조회 → Validation 조회 → RAG 쿼리(`"{상호} {품목들} 매입세액공제"`, top5) → GPT(system+user, `response_format: json_object`) → `LlmDeductionResult` 파싱 → Deduction **upsert** |
| `getDeductionByReceiptId` | public | `(receiptId, userId): Promise<Deduction>` | 영수증/공제 조회(없으면 404) |
| `getUserDeductionSummary` | public | `(userId)` | 사용자 전체 영수증·공제 집계. 반환 `{ total_receipts, deductible_count, non_deductible_count, pending_count, total_deductible_amount, total_vat_amount }` |
| `getRefundDate` | public | `(userId)` | 현재 분기 신고기한 +30일 = 예상 환급일, 공제 가능 금액 합계 계산. 반환 `{ period, filing_deadline, expected_refund_date, estimated_refund_amount, is_refundable, note }` |
| `getFilingDeadlineInfo` | private | `(date: Date): { filingDeadline: Date; periodLabel: string }` | 월로 분기 판단 후 신고기한·분기 라벨 반환 |
| `formatDate` | private | `(date: Date): string` | `YYYY-MM-DD` 포맷 |

**LLM 프롬프트**: system=부가세 전문 AI(JSON 강제), user=영수증 정보 + 사업자 검증 결과 + RAG 조문. `response_format: { type: 'json_object' }`.

**환급일 계산** (`getFilingDeadlineInfo`, 월 기준):

| 분기 | 신고기한 | 예상 환급일(+30일) |
|---|---|---|
| 1분기(1~3월) | 당해 4/25 | 5월 하순 |
| 2분기(4~6월) | 당해 7/25 | 8월 하순 |
| 3분기(7~9월) | 당해 10/25 | 11월 하순 |
| 4분기(10~12월) | 익년 1/25 | 익년 2월 하순 |

> 매출세액 데이터가 없어 `is_refundable`은 공제 가능 매입세액 합계(>0) 기준으로만 판단된다.

#### 컨트롤러 (`DeductionController`)

생성자: `private readonly deductionService`. 클래스에 `@UseGuards(JwtAuthGuard)`.

| Method | Path | 핸들러 | 반환 |
|---|---|---|---|
| `POST` | `/deduction/analyze/:receipt_id` | `analyzeDeduction` | `{ receipt_id, is_deductible, confidence_score, reason, related_law, applicable_rate, deductible_amount }` |
| `GET` | `/deduction/user/summary` | `getUserSummary` | 집계 통계 객체 |
| `GET` | `/deduction/refund-date` | `getRefundDate` | 환급 예상 객체 |
| `GET` | `/deduction/:receipt_id` | `getDeduction` | 위 + `created_at` |

> ⚠️ **라우트 순서**: `GET /deduction/user/summary`, `GET /deduction/refund-date`는 반드시 `GET /deduction/:receipt_id`보다 **먼저** 선언되어야 한다. NestJS는 선언 순서로 매칭하므로 순서가 바뀌면 리터럴 경로가 `:receipt_id`로 캡처된다. (현재 코드는 올바른 순서.)

---

### 8.9 Reports Module

**경로**: `src/reports/` · **prefix**: `/reports` · **인증**: 클래스 단위 `@UseGuards(JwtAuthGuard)`

#### 모듈 (`ReportsModule`)

- `imports`: `TypeOrmModule.forFeature([Report, Receipt, Deduction])`, `ConfigModule`, `S3Module`
- `controllers`: `[ReportsController]`
- `providers`/`exports`: `[ReportsService]`

#### DTO (`dto/report.dto.ts`)

```typescript
export class GenerateReportDto {
  @IsDateString()  period_start: string;   // 'YYYY-MM-DD'
  @IsDateString()  period_end: string;
  @IsIn(['general', 'simplified'])  report_type: 'general' | 'simplified';
}

// 정의되어 있으나 현재 컨트롤러/서비스에서 미사용
export class ConfirmReportDto {
  @IsBoolean()   confirmed: boolean;
  @IsOptional()  corrections?: { total_output_tax?: number; total_input_tax?: number };
}
```

#### `ReportsService`

- 모듈 상단: `const PDFDocument = require('pdfkit') as typeof import('pdfkit')` (CommonJS — ESM import 금지).
- 생성자: `@InjectRepository(Report) reportsRepository`, `@InjectRepository(Receipt) receiptsRepository`, `@InjectRepository(Deduction) deductionsRepository`, `s3Service: S3Service`, `configService: ConfigService`.
- 생성자 본문: `koreanFontPath` 결정 — `PDF_FONT_PATH`(존재 시) → `process.cwd()/assets/fonts/NanumGothic.ttf`(존재 시) → `null`(Helvetica 폴백).

| 메서드 | 접근 | 시그니처 | 역할 |
|---|---|---|---|
| `generateReport` | public | `(userId, dto: GenerateReportDto): Promise<Report>` | 기간 내 `is_deductible=true` 영수증 QueryBuilder 조회 → 매입처(business_number ‖ store_name)별 `SupplierGroup` 그룹화 + `total_input_tax` 누적 → `total_output_tax=0`, `final_tax=output-input` → Report 저장 → `buildPdf` → S3 업로드 → `pdf_url` 갱신 재저장 |
| `getReportById` | public | `(reportId, userId): Promise<Report>` | 소유자 검증 상세(없으면 404) |
| `getReportPdfUrl` | public | `(reportId, userId): Promise<{ pdf_url }>` | `pdf_url` 없으면 404, 있으면 반환 |
| `buildPdf` | private | `(report: Report): Promise<Buffer>` | pdfkit로 A4 PDF 스트림 생성 → Buffer concat. 제목·신고정보·매출세액·매입세액·납부(환급)세액·매입처별 합계표·면책 고지 렌더링. 한글 폰트 등록(`koreanFontPath` 존재 시) |
| `formatDate` | private | `(date: Date): string` | `YYYY-MM-DD` 포맷 |

**`buildPdf` 렌더링 구성**: 제목 `부가가치세 신고서` + 과세유형 라벨(`simplified`→간이과세자, else 일반과세자), 신고 기간/번호/작성일, 구분선, `[매출세액]`(공급가액=세액/0.1, 세액), `[매입세액]`, `[납부(환급)세액]`(밑줄), `[매입처별 세금계산서 합계표]`(컬럼: 상호명/사업자번호/공급가액/세액 + 합계행), 하단 회색 면책 문구. 금액은 `toLocaleString('ko-KR')`.

> `total_output_tax`는 현재 항상 0(별도 매출 데이터 모듈 미연동).

#### 컨트롤러 (`ReportsController`)

생성자: `private readonly reportsService`. 클래스에 `@UseGuards(JwtAuthGuard)`.

| Method | Path | 핸들러 | 반환 |
|---|---|---|---|
| `POST` | `/reports/generate` | `generate` | `{ report_id, total_output_tax, total_input_tax, final_tax, pdf_url, is_user_confirmed, grouped_suppliers }` |
| `GET` | `/reports/:id` | `getOne` | `{ id, period_start, period_end, report_type, total_output_tax, total_input_tax, final_tax, grouped_suppliers, pdf_url, is_user_confirmed, created_at }` |
| `GET` | `/reports/:id/pdf` | `getPdfUrl` | `{ pdf_url }` |

---

## 9. 전체 API 엔드포인트 요약

| Method | Path | Auth | 설명 |
|---|---|---|---|
| `GET` | `/` | 없음 | 헬스/헬로 (`AppController.getHello`) |
| `POST` | `/auth/phone/send-otp` | 없음 | 휴대폰 OTP 발송 |
| `POST` | `/auth/phone/verify-otp` | 없음 | OTP 검증 → 본인인증 토큰 발급 |
| `POST` | `/auth/register` | 없음 | 회원가입(사업자 진위 확인 포함) |
| `POST` | `/auth/login` | 없음 | 로그인(JWT 발급) |
| `POST` | `/receipts/upload` | JWT | 영수증 이미지 업로드 + OCR |
| `POST` | `/receipts/manual` | JWT | 수기 영수증 입력 |
| `GET` | `/receipts` | JWT | 영수증 목록 |
| `GET` | `/receipts/:id` | JWT | 영수증 상세 |
| `PATCH` | `/receipts/:id/confirm` | JWT | OCR 결과 확정/수정 |
| `PATCH` | `/receipts/:id/image` | JWT | 이미지 재업로드 + OCR 재실행 |
| `POST` | `/validation/business` | JWT | 사업자번호 직접 검증 |
| `POST` | `/validation/receipt/:receipt_id` | JWT | 영수증 사업자번호 검증 + 저장 |
| `GET` | `/validation/receipt/:receipt_id` | JWT | 검증 결과 조회 |
| `POST` | `/rag/embed` | Admin Key | 세법 조문 임베딩 저장 |
| `POST` | `/rag/search` | JWT | 관련 세법 조문 검색 |
| `POST` | `/rag/query` | JWT | AI 세무 질의(법령 기반 답변, 재탐색 지원) |
| `POST` | `/deduction/analyze/:receipt_id` | JWT | 매입세액 공제 판단(LLM + RAG) |
| `GET` | `/deduction/user/summary` | JWT | 사용자 공제 집계 통계 |
| `GET` | `/deduction/refund-date` | JWT | 예상 환급 수령일 |
| `GET` | `/deduction/:receipt_id` | JWT | 공제 판단 결과 조회 |
| `POST` | `/reports/generate` | JWT | 신고서 생성 + PDF |
| `GET` | `/reports/:id` | JWT | 신고서 상세 |
| `GET` | `/reports/:id/pdf` | JWT | PDF URL 조회 |
| `GET` | `/api` | 없음 | Swagger UI |

기능 엔드포인트 **24개** + 루트 `GET /` + Swagger `GET /api`.

---

## 10. 인증 흐름

### 회원가입 (휴대폰 본인인증 + 사업자 진위 확인)

```
POST /auth/phone/send-otp   { phone }
  → OTP 생성·저장(TTL 5분), 콘솔 출력
  → { message }

POST /auth/phone/verify-otp { phone, otp }
  → OTP 검증 → phone_verified_token(UUID, TTL 10분) 발급·저장
  → { phone_verified_token }

POST /auth/register { email, password, store_name, business_number, phone_verified_token }
  → 토큰 유효/만료 확인
  → 이메일 중복 확인
  → 국세청 API 사업자 진위 확인 (ValidationService.validateBusiness)
  → bcrypt(10) 해시 → User 저장(phone은 토큰에서 추출)
  → { access_token, user }
```

### 로그인 및 이후 요청

```
POST /auth/login { email, password }
  → { access_token: "eyJ..." }

이후: Authorization: Bearer <access_token>
  → JwtAuthGuard → JwtStrategy.validate(payload)
       · payload instanceof Payload 가드
       · usersRepository.findOne({ id: payload.sub })
  → req.user = JwtUser { userId, email }
  → @CurrentUser()로 컨트롤러에서 사용
```

JWT Payload:
```json
{ "sub": "<User.id UUID>", "email": "user@example.com", "iat": ..., "exp": ... }
```

- `sub` = `User.id`(UUID). 서명/만료는 `JWT_SECRET` / `JWT_EXPIRES_IN`(기본 `7d`).

---

## 11. 인프라 구성

### Dockerfile (multi-stage)

```
builder (node:20-alpine)
  ├─ npm ci (devDeps 포함)
  └─ npm run build → dist/

production (node:20-alpine)
  ├─ ENV NODE_ENV=production
  ├─ npm ci --only=production && npm cache clean --force
  ├─ COPY dist/ from builder
  ├─ COPY assets/ (한글 폰트, 실패해도 빌드 계속: `|| true`)
  ├─ EXPOSE 3000
  └─ CMD ["node", "dist/main"]
```

### docker-compose.yml

| 서비스 | 이미지/빌드 | 포트 | 비고 |
|---|---|---|---|
| `app` | `./Dockerfile` (target: production) | `3000:3000` | `env_file: .env`, `db` healthy 후 시작, `restart: unless-stopped` |
| `db` | `pgvector/pgvector:pg16` | 내부 `5432` | env: `POSTGRES_DB=taxai`, `POSTGRES_USER/PASSWORD`. 볼륨 `pgdata`. healthcheck `pg_isready -U $DB_USER -d taxai` (10s/5s/5회) |
| `nginx` | `nginx:alpine` | `80`, `443` | `nginx.conf` 마운트(ro), `app` 의존 |

### nginx.conf

| 설정 | 값 | 이유 |
|---|---|---|
| `worker_connections` | 1024 | 동시 연결 |
| `limit_req_zone ... rate=30r/s` + `burst=50 nodelay` | Rate limit | API 남용 방지 |
| `proxy_read_timeout` / `proxy_send_timeout` | 120s | OCR·LLM 장시간 호출 허용 |
| `client_max_body_size` | 10m | multer 10MB 제한과 일치 |
| `upstream nestjs { server app:3000; }` | 프록시 대상 | 컨테이너 내부 통신 |
| HTTPS(443) 블록 | 주석 처리 | SSL 인증서 설정 후 활성화 |

프록시 헤더: `Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`, `Connection ""`.

### .dockerignore

`node_modules`, `dist`, `.env`, `.env.*`, `.git`, `coverage`, `*.log`, `.DS_Store`, `.vscode`, `.idea`, `README.md` 등.

---

## 12. 코드와 기존 문서 간 차이 메모

> 본 README는 **현재 소스 코드**를 기준으로 작성되었다. 과거 문서/주석과 어긋나는 지점을 기록한다.

1. **`VectorColumn()`의 `synchronize: false` 누락**
   `src/rag/types/vector-column.ts`의 JSDoc 주석은 "`synchronize: false`로 동기화 제외"라고 설명하나, 실제 `Column({ type: 'text', transformer: {...} })` 옵션에는 `synchronize: false`가 **포함되어 있지 않다**. `NODE_ENV === 'synchronize'` 환경에서 TypeORM이 이 컬럼을 관리 대상으로 삼아 의도와 다르게 동작할 수 있다.

2. **`ADMIN_API_KEY`가 `.env.example`에 없음**
   `AdminGuard`는 `ADMIN_API_KEY`를 읽어 `POST /rag/embed`를 보호하지만, `.env.example`에는 해당 변수가 정의되어 있지 않다. 미설정 시 가드는 모든 요청을 거부한다(`!expectedKey`).

3. **삭제된 모듈**: `insights`(GPT 분기별 인사이트)와 `timeseries`(`Timeseries`/`Prediction` 엔티티)는 현재 트리에서 제거되었다. `AppModule`·DB 엔티티·API에 더 이상 존재하지 않는다.

4. **전역 `ValidationPipe` 미등록**: `main.ts`에 전역 파이프가 없어 DTO의 `class-validator` 데코레이터는 자동 검증되지 않는다(검증 강제 시 추가 필요).

5. **`AppController`(`GET /`)**: 단순 `"Hello World!"` 반환 엔드포인트로 헬스 체크 용도. 과거 문서에서는 누락되어 있었다.
