import { apiClient } from "./client";
import { getReceipt, type ReceiptDetails, type ReceiptReview } from "./receipts";

export interface TransactionApi {
  id: number;
  receipt_id: number | null;
  direction: "purchase" | "sales";
  transaction_date: string;
  vendor: string;
  description: string;
  purpose: string | null;
  total_amount: number;
  supply_amount: number | null;
  vat_amount: number | null;
  evidence_type: string;
  is_fixed_asset: boolean;
  state: string;
  review_status: string;
  analysis_reason: string | null;
  legal_references_json: string;
  deleted_at: string | null;
  permanent_delete_requested_at: string | null;
  retention_status: "required" | "not_required" | "under_review";
}

export interface AnalysisRunApi {
  id: string;
  status: "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED" | "CANCELLED";
  result_json: string | null;
  error_code: string | null;
  error_message: string | null;
  attempts: number;
}

export interface TaxEstimateApi {
  period: string;
  tax_type: "general" | "simplified";
  status: "COMPLETE" | "PARTIAL" | "UNAVAILABLE";
  output_vat: number | null;
  eligible_input_vat: number | null;
  deemed_input_vat: number | null;
  payable_estimate: number | null;
  included_transaction_count: number;
  caution_transaction_count: number;
  uncalculated_transaction_count: number;
  notes: string[];
  sales_aggregate_status?: string | null;
}

export interface TaxProfileApi {
  entity_type: "individual" | "corporation" | null;
  industry_category: "food_service" | "manufacturing" | "other" | null;
  industry_subtype: "restaurant" | "taxable_entertainment" | "specified_mill" | "other" | null;
  is_sme: boolean | null;
  simplified_industry_rate: number | null;
  taxable_sales_h1: number | null;
  taxable_sales_h2: number | null;
  deemed_related_taxable_sales_h1: number | null;
  deemed_related_taxable_sales_h2: number | null;
  business_start_date: string | null;
  business_end_date: string | null;
  suspension_periods: { start_date: string; end_date: string }[];
  tax_type_change_date: string | null;
  changed_to_tax_type: "general" | "simplified" | null;
  confirmed: boolean;
  confirmed_at: string | null;
}

export interface AsyncJobApi {
  id: string;
  job_type: "ocr" | "pdf" | "vat_return";
  status: "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED";
  result_json: string | null;
  error_code: string | null;
  error_message: string | null;
  attempts: number;
}

export type TaxProfileInput = Omit<TaxProfileApi, "confirmed_at"> & { confirmed: boolean };

export interface TransactionInput {
  direction: "purchase" | "sales";
  transaction_date: string;
  vendor: string;
  description: string;
  purpose?: string | null;
  evidence_type: "tax_invoice" | "card_receipt" | "cash_receipt" | "tax_free_receipt" | "manual" | "unknown";
  business_related: boolean | null;
  total_amount: number;
  supply_amount: number | null;
  vat_amount: number | null;
  deemed_input_supply?: number;
  deemed_input_eligible?: boolean | null;
  deemed_input_document_type?: "purchase_invoice" | "card_statement" | "farmer_direct" | "import_declaration" | null;
  tax_treatment: "standard" | "zero" | "exempt" | "unknown";
}

export async function createTransactionFromReceipt(receiptId: number, input: TransactionInput): Promise<TransactionApi> {
  const { data } = await apiClient.post<TransactionApi>(`/v2/transactions/from-receipt/${receiptId}`, input);
  return data;
}

export async function confirmTransaction(id: number): Promise<TransactionApi> {
  const { data } = await apiClient.post<TransactionApi>(`/v2/transactions/${id}/confirm`);
  return data;
}

// 보관함 '수정하기': 영수증 확인본과 거래 값을 함께 고친다.
export async function editTransactionReceipt(id: number, document: ReceiptReview["document"], details?: ReceiptDetails): Promise<TransactionApi> {
  const { data } = await apiClient.put<TransactionApi>(`/v2/transactions/${id}/receipt-document`, { document, details });
  return data;
}

// 보관함에서 영수증을 누르면 별도 확인 화면 없이, 추출 결과 확인에서 저장한 값 그대로 거래를 만들고 확정한다.
export async function confirmTransactionFromReceipt(receiptId: number): Promise<TransactionApi> {
  const receipt = await getReceipt(receiptId);
  const fields = receipt.recognition?.document?.fields;
  const number = (value: unknown) => typeof value === "number" ? Math.round(value) : null;
  const tax = receipt.review?.tax_treatment ?? "unknown";
  const transaction = await createTransactionFromReceipt(receiptId, {
    direction: receipt.direction,
    transaction_date: receipt.date ?? "",
    vendor: (receipt.vendor ?? "").trim(),
    description: receipt.details?.items?.map((item) => item.name).join(", ") ?? "",
    purpose: receipt.review?.purpose?.trim() || null,
    evidence_type: tax === "exempt" ? "tax_free_receipt" : receipt.review?.evidence_type ?? "unknown",
    business_related: receipt.review?.business_related ?? null,
    total_amount: Math.round(receipt.amount ?? 0),
    supply_amount: number(fields?.supply_amount),
    vat_amount: number(fields?.vat_amount),
    tax_treatment: tax,
  });
  return confirmTransaction(transaction.id);
}

export async function listTrash(): Promise<TransactionApi[]> {
  const { data } = await apiClient.get<TransactionApi[]>("/v2/trash");
  return data;
}

export async function listTransactions(direction: "purchase" | "sales" = "purchase"): Promise<TransactionApi[]> {
  const { data } = await apiClient.get<TransactionApi[]>("/v2/transactions", { params: { direction } });
  return data;
}

export async function moveTransactionToTrash(id: number): Promise<TransactionApi> {
  const { data } = await apiClient.delete<TransactionApi>(`/v2/transactions/${id}`);
  return data;
}

export async function createAnalysisRun(transactionIds: number[]): Promise<AnalysisRunApi> {
  const { data } = await apiClient.post<AnalysisRunApi>("/v2/analysis-runs", { transaction_ids: transactionIds });
  return data;
}

// 신고서 (12) 고정자산매입 칸 배정용. 공제 분석 결과는 바뀌지 않는다.
export async function setFixedAsset(transactionId: number, isFixedAsset: boolean): Promise<TransactionApi> {
  const { data } = await apiClient.put<TransactionApi>(`/v2/transactions/${transactionId}/fixed-asset`, { is_fixed_asset: isFixedAsset });
  return data;
}

export interface FilingInputApi {
  period: string;
  preliminary_notice_tax: number | null;
}

export async function getFilingInput(period: string): Promise<FilingInputApi> {
  const { data } = await apiClient.get<FilingInputApi>(`/v2/filing-inputs/${period}`);
  return data;
}

export async function saveFilingInput(period: string, preliminaryNoticeTax: number | null): Promise<FilingInputApi> {
  const { data } = await apiClient.put<FilingInputApi>(`/v2/filing-inputs/${period}`, { preliminary_notice_tax: preliminaryNoticeTax });
  return data;
}

export async function cancelAnalysisRun(runId: string): Promise<AnalysisRunApi> {
  const { data } = await apiClient.post<AnalysisRunApi>(`/v2/analysis-runs/${runId}/cancel`);
  return data;
}

export async function getAnalysisRun(id: string): Promise<AnalysisRunApi> {
  const { data } = await apiClient.get<AnalysisRunApi>(`/v2/analysis-runs/${id}`);
  return data;
}

export async function getTaxEstimate(period: string): Promise<TaxEstimateApi> {
  const { data } = await apiClient.get<TaxEstimateApi>("/v2/tax-estimates/2026", { params: { period } });
  return data;
}

export async function getTaxProfile(): Promise<TaxProfileApi> {
  const { data } = await apiClient.get<TaxProfileApi>("/v2/business/tax-profile");
  return data;
}

export async function saveTaxProfile(input: TaxProfileInput): Promise<TaxProfileApi> {
  const { data } = await apiClient.put<TaxProfileApi>("/v2/business/tax-profile", input);
  return data;
}

export async function createPdfJob(period: string): Promise<AsyncJobApi> {
  const { data } = await apiClient.post<AsyncJobApi>("/v2/pdf-jobs", null, { params: { period, reviewed: true } });
  return data;
}

// 부가세 신고서(별지 제21호서식) PDF. 완료되면 result_json에 검증 결과가 들어 있다.
export async function createVatReturnJob(period: string): Promise<AsyncJobApi> {
  const { data } = await apiClient.post<AsyncJobApi>("/v2/vat-return-jobs", null, { params: { period, reviewed: true } });
  return data;
}

export interface VatReturnResult {
  payable: number;
  notes: string[];
  verification: { status: "skipped" | "error" | "passed" | "mismatch"; message: string; mismatches?: { field: string; label: string; expected: string; read: string }[] };
}

export async function getAsyncJob(id: string): Promise<AsyncJobApi> {
  const { data } = await apiClient.get<AsyncJobApi>(`/v2/jobs/${id}`);
  return data;
}

export async function downloadPdfJob(id: string): Promise<Blob> {
  const { data } = await apiClient.get<Blob>(`/v2/pdf-jobs/${id}/download`, { responseType: "blob" });
  return data;
}

export async function restoreTransaction(id: number): Promise<TransactionApi> {
  const { data } = await apiClient.post<TransactionApi>(`/v2/trash/${id}/restore`);
  return data;
}

// 휴지통의 거래와 연결된 영수증·사진을 지운다. 되돌릴 수 없다.
export async function deleteTransactionPermanently(id: number): Promise<void> {
  await apiClient.delete(`/v2/trash/${id}`);
}

export interface FilingReadiness {
 period: string; ready: boolean; checks: {business:boolean; transactions:boolean; deductions:boolean; estimate:boolean};
 total:number; unconfirmed:number; pending:number; deductible:number; nondeductible:number; first_receipt_id:number|null;
}
export const getFilingReadiness = (period:string) => apiClient.get<FilingReadiness>("/v2/filing-readiness", {params:{period}}).then(r=>r.data);
