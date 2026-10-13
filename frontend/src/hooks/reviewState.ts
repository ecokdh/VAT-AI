import type { TransactionApi } from "../api/transactions";
import type { ReceiptProcessingApi } from "../api/receipts";
// 신고 기간: [시작 월, 끝 월, 표시 이름]
const PERIODS: Record<string, [number, number, string]> = {
  "2026-Q1": [1, 3, "2026년 1~3월"],
  "2026-H1": [1, 6, "2026년 1~6월"],
  "2026-Q3": [7, 9, "2026년 7~9월"],
  "2026-H2": [7, 12, "2026년 7~12월"],
  "2026-YEAR": [1, 12, "2026년 연간"],
};
export const isPeriod = (value: string | null): value is string => !!value && value in PERIODS;
export const periodOptions = (simplified: boolean) => simplified ? ["2026-YEAR"] : ["2026-Q1", "2026-H1", "2026-Q3", "2026-H2"];
export const defaultPeriod = () => new Date().getMonth() < 6 ? "2026-H1" : "2026-H2";
export const periodLabel = (period: string) => PERIODS[period]?.[2] ?? period;
export const inPeriod = (date: string | null, period: string) => {
  if (!date?.startsWith("2026-") || !isPeriod(period)) return false;
  const [from, to] = PERIODS[period];
  const month = Number(date.slice(5, 7));
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
