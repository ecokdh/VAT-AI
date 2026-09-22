export type TaxationType = "일반과세자" | "간이과세자";

export interface User {
  id: string;
  businessNumber: string;
  businessName: string;
  representativeName: string;
  email: string;
  businessType: string;
  taxationType: TaxationType;
}

export type ReceiptType = "매입" | "매출";
export type ReceiptStatus = "processing" | "completed" | "failed";

export interface Receipt {
  id: string;
  type: ReceiptType;
  issuedAt: string;
  supplierName: string;
  supplierBusinessNumber: string;
  itemSummary: string;
  supplyAmount: number;
  amount?: number | null;
  vatAmount: number;
  isExempt: boolean;
  status: ReceiptStatus;
}

export interface OcrResult {
  receiptId: string;
  supplierName: string;
  supplierBusinessNumber: string;
  itemName: string;
  supplyAmount: number;
  vatAmount: number;
  issuedAt: string;
  isExempt: boolean;
}

export interface Deduction {
  receiptId: string;
  isDeductible: boolean;
  reason: string;
  relatedLaws: { title: string; content: string }[];
  applicableRate: string;
  deductibleAmount: number;
  exemptSupplyAmount: number;
  capWarning?: string;
}

export interface ReportSummary {
  period: string;
  businessName: string;
  businessNumber: string;
  representativeName: string;
  businessType: string;
  taxationType: TaxationType;
  taxBase: number;
  salesTax: number;
  purchaseTaxInvoiceAmount: number;
  purchaseTax: number;
  presumptiveDeduction: number;
  purchaseTaxTotal: number;
  reductionTotal: number;
  additionalTaxTotal: number;
  finalTax: number;
  dueDate: string;
}
