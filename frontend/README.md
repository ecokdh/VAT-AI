# frontend

Track D 담당. React 19 + Vite 8 + TypeScript 7, react-router-dom, axios.

## 개발 서버 실행

```bash
npm install
npm run dev
```

## 구조

- `src/pages` — 화면 단위 컴포넌트 (기획서 5.7절 와이어프레임 기준)
  - `auth/` 로그인, 회원가입
  - `DashboardPage` 홈 대시보드
  - `CapturePage` 세금계산서/영수증 촬영
  - `receipts/` OCR 분석 중 → 추출 결과 확인/수정 → AI 세액 분석 결과
  - `storage/` 매입/매출 영수증 보관함
  - `reports/` 부가가치세 신고서 생성
- `src/components` — 화면 간 공유하는 UI 조각 (헤더, 요약 카드, 필터 칩, 거래 리스트 행 등)
- `src/mocks` — 아직 백엔드 API가 없는 C/D 화면에서 사용하는 목데이터
- `src/types` — 백엔드 엔티티(User, Receipt, Deduction, Report)에 대응하는 프론트 타입
- `src/styles` — 디자인 토큰(`tokens.css`) 및 공용 클래스(`ui.css`)

로그인·회원가입과 B트랙 영수증 업로드, OCR 처리 결과, 매입 영수증 목록은 `src/api`의 axios 클라이언트로 실제 백엔드 API를 호출한다. 세액 분석·신고서·매출 보관함처럼 백엔드 계약이 없는 화면은 아직 목데이터를 사용한다.
