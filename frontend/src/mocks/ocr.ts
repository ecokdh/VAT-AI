import type { OcrResult } from "../types";
import { processingReceipt } from "./receipts";

export const mockOcrResult: OcrResult = {
  receiptId: processingReceipt.id,
  supplierName: processingReceipt.supplierName,
  supplierBusinessNumber: processingReceipt.supplierBusinessNumber,
  itemName: processingReceipt.itemSummary,
  supplyAmount: processingReceipt.supplyAmount,
  vatAmount: processingReceipt.vatAmount,
  issuedAt: processingReceipt.issuedAt,
  isExempt: processingReceipt.isExempt,
};
