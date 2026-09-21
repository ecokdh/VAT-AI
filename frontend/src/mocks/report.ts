import type { ReportSummary } from "../types";
import { purchaseTotals, salesTotals } from "./receipts";
import { mockDeduction } from "./deduction";

const presumptiveDeduction = mockDeduction.deductibleAmount;
const purchaseTaxTotal = purchaseTotals.vatAmount + presumptiveDeduction;
const reductionTotal = 10_000;
const additionalTaxTotal = 0;
const finalTax = salesTotals.vatAmount - purchaseTaxTotal - reductionTotal + additionalTaxTotal;

export const mockReport: ReportSummary = {
  period: "2024년 1기 확정 (2024.01.01 ~ 2024.06.30)",
  businessName: "소상공인 푸드 코리아",
  businessNumber: "123-45-67890",
  representativeName: "김대표",
  businessType: "음식점업 · 한식 일반음식점",
  taxationType: "일반과세자",
  taxBase: salesTotals.supplyAmount,
  salesTax: salesTotals.vatAmount,
  purchaseTaxInvoiceAmount: purchaseTotals.supplyAmount,
  purchaseTax: purchaseTotals.vatAmount,
  presumptiveDeduction,
  purchaseTaxTotal,
  reductionTotal,
  additionalTaxTotal,
  finalTax,
  dueDate: "2024년 1기 확정 신고·납부 기한: 2024년 7월 25일(목). 전자신고 시 세액공제 10,000원이 자동 적용되었습니다.",
};
