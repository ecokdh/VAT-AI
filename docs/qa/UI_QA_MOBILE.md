# UI QA 및 모바일 화면 규격 — 2026-10-19

## 작업 분리

- 브랜치: `codex/ui-qa-polish` (커밋하지 않음)
- 작업 폴더: `C:/Users/Master/.codex/worktrees/ui-qa-polish/VAT-AI`
- 원본 `codex/track-ocr-qa` 및 테마 전용 `codex/ui-theme-refresh` 보존.
- QA 앱: http://localhost:5173/dashboard / API: http://localhost:8001
- 모바일 프레임: http://localhost:5173/qa/mobile-preview.html
- 가상 영수증 검토: http://localhost:5173/qa/fixture.html
- `frontend/qa`는 개발 전용 Vite 문서이며 프로덕션 빌드 진입점에 포함되지 않는다. 가상 데이터 어댑터는 실제 서버를 호출하지 않는다.
- QA DB는 테마 DB를 SQLite backup으로 복사한 `vat_ai_qa_preview.db`. 영수증 파일도 별도 복사.

## 화면 규격

| 항목 | 기준 |
|---|---|
| 디자인 기준 | 390 CSS px 너비, 참고 높이 844px |
| 스마트폰 세로 검토 | 320×568, 360×800, 390×844, 430×932 |
| 추가 검토 | 844×390 가로, 768×1024 태블릿 |
| 높이 | 고정하지 않음. 콘텐츠 스크롤 및 `dvh` 사용 |
| 영수증 | 850px 미만 1열. 사진 → 정보 → 목적 → 저장 순서 |
| 사진 고정 | 작은 화면 및 낮은 가로 화면에서는 해제 |
| 입력 글자 | 16px |
| 주요 버튼·헤더 아이콘 | 최소 높이 48px |
| 가장자리 | safe-area inset 반영, 확대 기능 유지 |

390px는 모든 기기를 고정시키는 값이 아니다. `width=device-width`와 유동 너비를 사용한다. 데스크톱 검토 브라우저의 세로 스크롤바가 15px를 차지하여 320px 뷰포트의 실제 콘텐츠 너비는 305px였다. 이 더 좁은 조건에서도 문서 가로 넘침이 없음을 확인했다.

기준 참고: [MDN viewport](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/meta/name/viewport), [Android layout basics](https://developer.android.com/design/ui/mobile/guides/layout-and-content/layout-basics).

## 반영 항목

- 회원가입 완료 → 로그인, 로그인 완료 → 홈. 사업 프로필 미작성 여부로 마이페이지에 보내던 분기 제거.
- 연도·신고기간 휠: 터치/스크롤·클릭·방향키 지원, 선택 완료 시 적용, 취소 시 유지.
- 기존 Q1/H1/Q3/H2 및 간이과세 YEAR 계산 범위 유지.
- 홈 공제/불공제 요약 → 해당 확정 매입 필터. 확인 필요 → 매입·매출 및 미확정 증빙 함께 표시.
- 예상 납부세액 아래 여백 축소.
- 닉네임: 신규 가입 입력, 마이페이지 수정, 홈 인사말 사용. 기존 계정은 ‘고객’ 및 설정 링크 표시.
- 대표자 이름과 닉네임 별도 저장. 국세청 대표자명·사업자번호·개업일자 진위확인. 가입 서버에서도 다시 검증, 실패 시 계정 생성 차단.
- 상호명 읽기 전용. API에서도 다른 상호로 변경 시 거부하며 사업 프로필·기존 분석에 부수 변경 없음.
- 사진 삭제 및 재선택 지원. 사진은 기존과 같이 브라우저에 저장.
- 마이페이지 아래 오른쪽 빨간색 로그아웃, 기존 확인창 유지.
- 분석하기 보라색 / 추가 확인 황갈색 / 결과 보기 녹색으로 구분.

## API / 마이그레이션

- `users.nickname` nullable 20자 필드, Alembic `a10c19aa0013` (`f2b3c4d5e6a7` 다음).
- 기존 사용자의 실명을 닉네임으로 자동 복사하지 않는다.
- `PATCH /auth/me`는 닉네임만 수정, 공백 정리 후 2~20자. 다른 필드는 거부.
- `POST /business/verify-identity`: 사업자번호, 대표자명, 개업일자 입력.
- 가입 요청은 `tax_profile.business_start_date` 필수. 닉네임은 기존 API 클라이언트 호환을 위해 optional, 새 가입 UI에서는 필수.
- 새 가입의 `verification_status`는 `identity_verified`. 기존 계정의 검증 상태를 소급 변경하지 않음.
- `NTS_BUSINESS_VALIDATE_URL` 추가. 기존 NTS 키 사용, 해당 진위확인 서비스 사용 권한 필요.
- [국세청 서비스 명세](https://www.data.go.kr/data/15081808/openapi.do)를 참고. 실제 사업자 정보로 외부 조회는 이번 QA에서 실행하지 않았다.

## 검증 결과

- 백엔드 100개 통과: auth, business_registration, business_questions, qa4_flows, qa_polish, receipts, local_qa_flow, luna_local, luna_edge_cases_e2e.
- 프런트엔드 6개 통과, TypeScript 및 Vite 프로덕션 빌드 성공.
- lint 오류 없음. 기존 effect/Fast Refresh 관련 경고 10개 유지.
- DB 복사본에 실제 마이그레이션 성공.
- 브라우저: 6개 크기의 영수증 기본 화면 가로 넘침 없음. 320px 상세 품목·마이페이지 확장 폼 가로 넘침 없음.
- 가상 데이터: 확인 필요 4건 → 매입·매출 목록 4건, 공제 1건/불공제 1건 필터, 닉네임 저장, 사진 업로드 후 삭제, 상호 읽기 전용, 로그아웃 확인창 확인.
- 실제 로그인 계정: 홈/보관함 API 정상 로드, 기간 선택 적용 확인. QA 복사본에서 해당 계정의 거래는 0건.
- 남은 검증: 실제 Android Chrome/iOS Safari 기기의 키보드·카메라·노치 환경, 실제 국세청 진위확인 서비스 성공/불일치 응답. 브라우저 크기 검토는 실기기 검증과 구분한다.
