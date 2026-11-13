import type { ReactNode } from "react";
import "../styles/ledger.css";

type ResultKind = "deductible" | "nondeductible" | "review";

// 보관함 거래 카드: 이름·날짜·상태 / 금액·상세, 분석이 끝난 매입 거래만 아래에 결과 칸을 붙인다.
export function LedgerCard({ select, title, date, amount, status, statusClass, onDetail, detailDisabled, result }: {
  select?: ReactNode; title: string; date: string; amount: string; status: string; statusClass: string;
  onDetail: () => void; detailDisabled?: boolean; result?: { kind: ResultKind; onClick: () => void };
}) {
  return <article className="ledger-card2">
    <div className="ledger-card2__row">
      {select}
      <div className="ledger-card2__main"><strong>{title}</strong><small>{shortDate(date)}{status && <> · <span className={statusClass}>{status.replace(/^[✓◷]\s*/, "")}</span></>}</small></div>
      <div className="ledger-card2__side"><strong>{amount}</strong><button type="button" disabled={detailDisabled} onClick={onDetail}>상세 <span aria-hidden="true">›</span></button></div>
    </div>
    {result && <button type="button" className={`ledger-card2__result ledger-card2__result--${result.kind}`} onClick={result.onClick}>
      {result.kind === "review" ? "추가 확인사항 보기" : "분석 결과 보기"} <span aria-hidden="true">›</span>
    </button>}
  </article>;
}

// "2026-03-28" → "3월 28일". 날짜가 아닌 안내 문구는 그대로 둔다.
function shortDate(value: string) {
  return value.replace(/^\d{4}-(\d{2})-(\d{2})/, (_, month, day) => `${Number(month)}월 ${Number(day)}일`);
}
