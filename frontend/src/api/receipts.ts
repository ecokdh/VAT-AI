import { apiClient } from "./client";

export type ReceiptApiStatus = "done" | "failed" | "retake" | "needs_edit";

export interface ItemAmount {
  item_index: number;
  item_name: string;
  quantity: number | null;
  line_amount: number | null;
  unit_price: number | null;
  sources: Record<string, { kind: "printed" | "calculated" | "manual"; rule?: string }>;
}

export interface ReceiptApi {
  id: number;
  revision: number;
  transaction_id?: string | null;
  line_items: StructuredItem[];
  document: DocumentFacts;
  evidence_validation: { validation_status: string; missing_fields: string[]; conflicts: string[]; deduction_status: string };
  user_id: string;
  image_url: string;
  ocr_raw: string | null;
  vendor: string | null;
  amount: number | null;
  date: string | null;
  status: ReceiptApiStatus;
  quality_reason?: string | null;
  business_number?: string | null;
  supply_amount?: number | null;
  vat_amount?: number | null;
  taxable_supply_amount?: number | null;
  tax_exempt_amount?: number | null;
  transaction_amount?: number | null;
  payment_amount?: number | null;
  subtotal_amount?: number | null;
  item_amounts?: ItemAmount[];
  money_schema_version?: number;
  money_sources?: Record<string, { kind: "printed" | "calculated" | "manual"; rule?: string;
    state?: Evidence["state"]; boxes?: Evidence["boxes"]; confidence?: number | null; input_fields?: string[] }>;
  items?: string[];
  ocr_original?: string | null;
  confirmed?: boolean;
  created_at: string;
}

export interface Evidence {
  kind: "ocr" | "manual" | "calculated";
  state: "READ" | "ABSENT" | "FAILED" | "UNREVIEWED" | "NOT_APPLICABLE";
  boxes?: { x: number; y: number; width: number; height: number }[];
  confidence?: number | null;
  rule?: string | null;
}

export interface StructuredItem {
  id: string | null;
  name: string;
  original_name?: string | null;
  specification?: string | null;
  unit?: string | null;
  quantity: number | null;
  printed_unit_price: number | null;
  effective_unit_price?: number | null;
  line_amount: number | null;
  discount_amount?: number | null;
  tax_type: "UNKNOWN" | "TAXABLE" | "EXEMPT" | "ZERO_RATED";
  usage: "UNKNOWN" | "BUSINESS" | "PERSONAL" | "MIXED";
  user_note?: string | null;
  sources: Record<string, Evidence>;
}

export interface DocumentFacts {
  sources?: Record<string, Evidence>;
  discounts?: { id: string; kind: "DISCOUNT" | "COUPON"; scope: "ITEM" | "GROUP" | "TRANSACTION"; amount: number;
    item_ids: string[]; included_in_line_amounts: boolean | null; included_in_discount_id: string | null }[];
  adjustment_type?: "RETURN" | "CANCELLATION" | "CORRECTION" | null;
  document_type: "CARD_RECEIPT" | "CASH_RECEIPT" | "GENERAL_RECEIPT" | "TAX_INVOICE" | "INVOICE" | "UNKNOWN";
  supply_date?: string | null;
  document_issue_date?: string | null;
  payment_date?: string | null;
  approval_number?: string | null;
  transaction_datetime?: string | null;
  card_number_masked?: string | null;
  card_last4?: string | null;
  merchant_business_number?: string | null;
  customer_business_number?: string | null;
  date_candidates?: { raw: string; value: string; source: Evidence }[];
  [key: string]: unknown;
}

export function getReceiptImage(receiptId: number) {
  return apiClient.get<Blob>(`/receipts/${receiptId}/image`, { responseType: "blob" }).then(res => res.data);
}

export function uploadReceipt(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return apiClient.post<ReceiptApi>("/receipts", formData).then((res) => res.data);
}

export function listReceipts() {
  return apiClient.get<ReceiptApi[]>("/receipts").then((res) => res.data);
}

export function getReceipt(receiptId: number) {
  return apiClient.get<ReceiptApi>(`/receipts/${receiptId}`).then((res) => res.data);
}

export function updateReceiptOcr(
  receiptId: number,
  payload: Partial<ReceiptApi> & {
    base_revision: number;
    field_states?: Record<string, Evidence["state"]>;
    base_amount?: number | null;
    base_supply_amount?: number | null;
    base_vat_amount?: number | null;
    base_taxable_supply_amount?: number | null;
    base_tax_exempt_amount?: number | null;
    base_transaction_amount?: number | null;
    base_payment_amount?: number | null;
    base_subtotal_amount?: number | null;
    base_items?: string[];
    base_item_amounts?: ItemAmount[];
  },
) {
  return apiClient
    .patch<ReceiptApi>(`/receipts/${receiptId}/ocr`, payload)
    .then((res) => res.data);
}

export function confirmReceiptOcr(receiptId: number, baseRevision: number) {
  return apiClient
    .post<ReceiptApi>(`/receipts/${receiptId}/ocr/confirm`, { confirmed: true, base_revision: baseRevision })
    .then((res) => res.data);
}
