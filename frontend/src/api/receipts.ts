import { apiClient } from "./client";

export type ReceiptApiStatus = "processing" | "done" | "failed";

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
}

export interface ReceiptProcessingApi extends ReceiptApi {
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

export interface ReceiptExtractionInput { vendor: string; amount: number; date: string; }

export function uploadReceipt(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return apiClient.post<ReceiptApi>("/receipts", formData).then((res) => res.data);
}

export async function enqueueReceiptOcr(file: File): Promise<{ job_id: string; receipt_id: number; status: "PENDING" }> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await apiClient.post("/v2/receipt-jobs", formData);
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
