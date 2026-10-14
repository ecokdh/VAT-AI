import { apiClient } from "./client";

export type ReceiptApiStatus = "processing" | "done" | "needs_edit" | "unsupported" | "retake" | "failed";

export interface ReceiptRecognition {
  engine: string;
  original_document?: {items: ReviewedItem[]};
  error_code?: string;
  value_source?: string;
  document?: {
    fields: Record<string, string | number | null>;
    items: Array<{name: string; raw_name?: string | null; source_row?: number | null; quantity: number | null; unit_price: number | null; line_amount: number | null; row_type: string; parent_row: number | null}>;
    conflicts: string[];
    uncertain: string[];
  };
}

export type ReviewedItem = NonNullable<ReceiptRecognition['document']>['items'][number];
export interface ReceiptReview {
  document: { fields: Record<string, string | number | null>; items: ReviewedItem[] };
  question_answers?: Record<string,string>;
  purpose: string | null;
  evidence_type: 'tax_invoice' | 'card_receipt' | 'cash_receipt' | 'tax_free_receipt' | 'manual' | 'unknown';
  business_related: boolean | null;
  tax_treatment: 'standard' | 'zero' | 'exempt' | 'unknown';
}

export interface ReceiptApi {
  id: number;
  user_id: string;
  image_url: string;
  ocr_raw: string | null;
  vendor: string | null;
  amount: number | null;
  date: string | null;
  status: ReceiptApiStatus;
  created_at: string;
  recognition?: ReceiptRecognition | null;
  review?: ReceiptReview | null;
  doc_type?: string | null;
  support_status?: string | null;
  readability_issues?: string[];
  affected_regions?: string[];
  issue_code?: string | null;
  guide_message?: string | null;
  classification_version?: string | null;
}

export interface ReceiptLineItem {name:string;quantity:number|null;unit_price:number|null;amount:number|null;}
export interface ReceiptDetails {
 business_number?:string|null;address?:string|null;phone?:string|null;payment_method?:string|null;
 approval_number?:string|null;receipt_number?:string|null;supply_amount?:number|null;vat_amount?:number|null;tax_free_amount?:number|null;
 items?:ReceiptLineItem[];additional_fields?:{label:string;value:string}[];
}
export interface ReceiptProcessingApi extends ReceiptApi {
  details: ReceiptDetails;
  direction: "purchase" | "sales";
  processing_stage: string | null;
  processing_progress: number;
  stage_statuses: Record<string, "pending" | "processing" | "completed" | "failed" | "skipped">;
  ocr_warnings: string[];
  ocr_pipeline_name: string | null;
  ocr_pipeline_version: string | null;
  ocr_missing_fields: string[];
  extraction_confirmed: boolean;
  ocr_user_attempts: number;
  retention_status: string;
}

export interface ReceiptExtractionInput {
  vendor: string; amount: number; date: string;
  details?: ReceiptDetails;
  document?: ReceiptReview['document'];
  question_answers?: Record<string,string>;
  purpose?: string | null;
  evidence_type?: ReceiptReview['evidence_type'];
  business_related?: boolean | null;
  tax_treatment?: ReceiptReview['tax_treatment'];
}

export function uploadReceipt(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return apiClient.post<ReceiptApi>("/receipts", formData).then((res) => res.data);
}

export async function enqueueReceiptOcr(file: File, direction: "purchase" | "sales"): Promise<{ job_id: string; receipt_id: number; status: "PENDING" }> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("direction", direction);
  const { data } = await apiClient.post("/v2/receipt-jobs", formData);
  return data;
}

export async function getReceiptImage(receiptId: number): Promise<Blob> {
  const { data } = await apiClient.get<Blob>(`/v2/receipts/${receiptId}/image`, { responseType: "blob" });
  return data;
}

export function listReceipts() {
  return apiClient.get<ReceiptApi[]>("/receipts").then((res) => res.data);
}

export function getReceipt(receiptId: number) {
  return apiClient.get<ReceiptProcessingApi>(`/v2/receipts/${receiptId}`).then((res) => res.data);
}

export function listReceiptInbox() {
  return apiClient.get<ReceiptProcessingApi[]>("/v2/receipt-inbox").then((res) => res.data);
}

export function confirmReceiptExtraction(receiptId: number, input: ReceiptExtractionInput) {
  return apiClient.post<ReceiptProcessingApi>(`/v2/receipts/${receiptId}/confirm-extraction`, input).then((res) => res.data);
}

export function retryReceiptOcr(receiptId: number) {
  return apiClient.post<{ receipt_id: number; job_id: string; status: "PENDING"; attempt: number }>(`/v2/receipts/${receiptId}/retry`).then((res) => res.data);
}
