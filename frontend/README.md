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
- `src/mocks` — 1주차 스켈레톤 단계용 목데이터 (백엔드 연동 전까지 사용)
- `src/types` — 백엔드 엔티티(User, Receipt, Deduction, Report)에 대응하는 프론트 타입
- `src/styles` — 디자인 토큰(`tokens.css`) 및 공용 클래스(`ui.css`)

목데이터를 실제 API 호출로 교체할 때는 `src/mocks`를 참고해 axios 클라이언트로 옮기면 된다.
