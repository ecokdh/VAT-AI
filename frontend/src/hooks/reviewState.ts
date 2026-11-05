import type { TransactionApi } from "../api/transactions";
import type { ReceiptProcessingApi } from "../api/receipts";
// Labels describe the actual tax interval; H1/H2 are half-year final filings.
const INTERVALS: Record<string, [number, number, string]> = {
 Q1:[1,3,"1분기 (1~3월)"], H1:[1,6,"1기 확정 (1~6월)"],
 Q3:[7,9,"3분기 (7~9월)"], H2:[7,12,"2기 확정 (7~12월)"], YEAR:[1,12,"연간 (1~12월)"],
};
export const isPeriod = (value: string | null): value is string => !!value && /^(2025|2026)-(Q1|H1|Q3|H2|YEAR)$/.test(value);
export const periodOptions = (simplified: boolean) => [2026,2025].flatMap(year => (simplified ? ["YEAR"] : ["Q1","H1","Q3","H2"]).map(part=>`${year}-${part}`));
export const defaultPeriod = () => new Date().getMonth() < 6 ? "2026-H1" : "2026-H2";
export const periodLabel = (period: string) => isPeriod(period) ? `${period.slice(0,4)}년 ${INTERVALS[period.slice(5)][2]}` : period;
export const inPeriod = (date: string | null, period: string) => {
 if (!date || !isPeriod(period) || date.slice(0,4) !== period.slice(0,4)) return false;
 const [from,to] = INTERVALS[period.slice(5)]; const month=Number(date.slice(5,7));
 return from <= month && month <= to;
};
export const needsReview = (row: TransactionApi) => row.state !== "confirmed" || (row.direction === "purchase" && !["analyzed", "excluded"].includes(row.review_status));
const NOT_ANALYZED = ["not_analyzed", "pending", "stale"];
const AMBIGUOUS = ["caution", "insufficient_info"];
export function matchesReviewStatus(row: TransactionApi, status: string) {
  // waiting: 아직 공제 분석을 받지 않은 거래, caution: 분석 결과가 애매해 추가 확인이 필요한 거래
  if (status === "waiting") return row.state !== "confirmed" || (row.direction === "purchase" && NOT_ANALYZED.includes(row.review_status));
  if (status === "caution") return row.direction === "purchase" && row.state === "confirmed" && AMBIGUOUS.includes(row.review_status);
  if (status === "review") return needsReview(row);
  if (status === "done") return !needsReview(row);
  if (status === "deductible" || status === "nondeductible") return row.direction === "purchase" && row.state === "confirmed" && row.review_status === (status === "deductible" ? "analyzed" : "excluded");
  return true;
}
export const REVIEW_LABELS: Record<string,string> = { pending:"분석 대기",not_analyzed:"분석 대기",analyzed:"공제 가능",caution:"추가 확인 필요",insufficient_info:"정보 부족",excluded:"공제 불가능",stale:"분석 대기" };
export const reviewLabel = (row: TransactionApi) => row.direction === "purchase" ? REVIEW_LABELS[row.review_status] ?? "확인 필요" : row.state === "confirmed" ? "✓ 확정" : "◷ 확인 필요";
export const reviewStatusClass = (row: TransactionApi) => row.direction === "purchase" && row.review_status === "excluded" ? "status-label--danger" : needsReview(row) ? "status-label--review" : "status-label--done";

// 보관함 목록과 '전체 보기'가 같은 기간·월·상태·정렬 조건으로 거래를 고른다.
export type LedgerFilter = { period: string; month: string; status: string; order: string };
export function filterLedger(rows: TransactionApi[], inbox: ReceiptProcessingApi[], { period, month, status, order }: LedgerFilter) {
  const inMonth = (date: string | null) => !month || !date || Number(date.slice(5,7)) === Number(month);
  const transactions = rows.filter(r => (period === "all" || inPeriod(r.transaction_date, period)) && inMonth(r.transaction_date) && matchesReviewStatus(r, status))
    .sort((a,b) => order === "amount" ? b.total_amount-a.total_amount : order === "oldest" ? a.transaction_date.localeCompare(b.transaction_date) : b.transaction_date.localeCompare(a.transaction_date));
  const receipts = inbox.filter(r => (period === "all" || !r.date || inPeriod(r.date, period)) && ["all","review","waiting"].includes(status) && inMonth(r.date));
  return { transactions, receipts };
}

export function summarizeReview(rows: TransactionApi[], inbox: ReceiptProcessingApi[], period: string) {
  const transactions = rows.filter(row => !row.deleted_at && inPeriod(row.transaction_date, period));
  const receipts = inbox.filter(row => !row.date || inPeriod(row.date, period));
  const unconfirmed = receipts.length + transactions.filter(row => row.state !== "confirmed").length;
  const pending = transactions.filter(row => row.state === "confirmed" && needsReview(row)).length;
  const total = transactions.length + receipts.length;
  const firstDirection = receipts[0]?.direction ?? transactions.find(row => row.state !== "confirmed")?.direction ?? "purchase";
  return { total, unconfirmed, pending, ready: total - unconfirmed - pending, firstDirection };
}
