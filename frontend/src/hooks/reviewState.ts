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
export function summarizeReview(rows: TransactionApi[], inbox: ReceiptProcessingApi[], period: string) {
  const transactions = rows.filter(row => !row.deleted_at && inPeriod(row.transaction_date, period));
  const receipts = inbox.filter(row => !row.date || inPeriod(row.date, period));
  const unconfirmed = receipts.length + transactions.filter(row => row.state !== "confirmed").length;
  const pending = transactions.filter(row => row.state === "confirmed" && needsReview(row)).length;
  const total = transactions.length + receipts.length;
  const firstDirection = receipts[0]?.direction ?? transactions.find(row => row.state !== "confirmed")?.direction ?? "purchase";
  return { total, unconfirmed, pending, ready: total - unconfirmed - pending, firstDirection };
}
