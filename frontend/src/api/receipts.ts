import { apiClient } from "./client";

export type ReceiptApiStatus = "done" | "failed";

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
