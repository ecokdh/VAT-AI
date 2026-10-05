import { apiClient } from "./client";
import type { ReceiptApi, StructuredItem } from "./receipts";

export interface TransactionApi {
  id: string;
  revision: number;
  workflow_status: string;
  original_transaction_id: string | null;
  adjustment_type: string | null;
  facts: { vendor?: string | null; total_amount?: number | null; date?: string | null; ocr_confirmed?: boolean };
  receipts: ReceiptApi[];
  canonical_line_items: StructuredItem[];
  canonical_receipt_id: number | null;
  evidence_validation: { validation_status: string; conflicts: string[] };
}
export interface DuplicateIssue {
  id: string;
  reason: string;
  resolved: boolean;
  active: boolean;
  receipts: { id: number; revision: number; transaction_id: string | null }[];
}
export const listTransactions = () => apiClient.get<TransactionApi[]>("/transactions").then(r => r.data);
export const getTransaction = (id: string) => apiClient.get<TransactionApi>(`/transactions/${id}`).then(r => r.data);
export const listDuplicateIssues = () => apiClient.get<DuplicateIssue[]>("/reconciliation/issues").then(r => r.data);
export const updateItemUsage = (id: string, itemId: string, revision: number, usage: StructuredItem["usage"]) =>
  apiClient.patch<TransactionApi>(`/transactions/${id}/line-items/${itemId}`, { base_revision: revision, usage }).then(r => r.data);
export const linkOriginal = (id: string, revision: number, original: TransactionApi) =>
  apiClient.patch<TransactionApi>(`/transactions/${id}`, {
    base_revision: revision, original_transaction_id: original.id, original_revision: original.revision,
  }).then(r => r.data);
export const resolveDuplicate = (issue: DuplicateIssue, canonical: TransactionApi | null, transactions: TransactionApi[]) =>
  apiClient.post(`/reconciliation/issues/${issue.id}/resolve`, canonical ? {
    action: "MERGE", canonical_transaction_id: canonical.id,
    transaction_revisions: Object.fromEntries(transactions.map(t => [t.id, t.revision])),
    receipt_revisions: Object.fromEntries(transactions.flatMap(t => t.receipts.map(r => [r.id, r.revision]))),
  } : { action: "SEPARATE" });
export const linkEvidence = (canonical: TransactionApi, source: TransactionApi, receipt: ReceiptApi, originalRevision?: number, relatedTransactions: TransactionApi[] = []) =>
  apiClient.post<TransactionApi>(`/transactions/${canonical.id}/evidence`, {
    receipt_id: receipt.id, base_revision: canonical.revision, receipt_revision: receipt.revision,
    source_transaction_revision: source.revision,
    original_revision: originalRevision,
    related_transaction_revisions: Object.fromEntries(relatedTransactions.map(t => [t.id, t.revision])),
    source_receipt_revisions: Object.fromEntries(source.receipts.map(r => [r.id, r.revision])),
  }).then(r => r.data);
