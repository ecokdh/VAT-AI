import { apiClient } from "./client";

export interface TransactionApi {
  id: number;
  receipt_id: number | null;
  direction: "purchase" | "sales";
  transaction_date: string;
  vendor: string;
  description: string;
  total_amount: number;
  supply_amount: number | null;
  vat_amount: number | null;
  state: string;
  review_status: string;
  deleted_at: string | null;
  permanent_delete_requested_at: string | null;
  retention_status: "required" | "not_required" | "under_review";
}

export interface AnalysisRunApi {
  id: string;
  status: "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED";
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
  job_type: "ocr" | "pdf";
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
  const { data } = await apiClient.post<AsyncJobApi>("/v2/pdf-jobs", null, { params: { period } });
  return data;
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

export async function requestPermanentDelete(id: number): Promise<TransactionApi> {
  const { data } = await apiClient.post<TransactionApi>(`/v2/trash/${id}/permanent-delete-request`);
  return data;
}
