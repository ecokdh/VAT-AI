import type { TransactionApi } from "../api/transactions";
import type { ReceiptProcessingApi } from "../api/receipts";
export const periodLabel = (period: string) => period === "2026-YEAR" ? "2026년 연간" : period === "2026-H1" ? "2026년 1기" : "2026년 2기";
export const inPeriod = (date: string | null, period: string) => !!date && date.startsWith("2026-") && (period === "2026-YEAR" || (Number(date.slice(5, 7)) <= 6) === (period === "2026-H1"));
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
