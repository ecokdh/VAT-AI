import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { isAxiosError } from "axios";
import { listReceipts, type ReceiptApi } from "../../api/receipts";
import { listTransactions } from "../../api/transactions";
import { StorageView } from "../../components/StorageView";
import type { Receipt } from "../../types";

function toReceiptView(receipt: ReceiptApi, includedInTotal: boolean): Receipt {
  const separated = receipt.money_schema_version === 2 || [receipt.taxable_supply_amount, receipt.tax_exempt_amount, receipt.transaction_amount, receipt.payment_amount, receipt.subtotal_amount].some(value => value != null);
  const confirmed = Boolean(receipt.confirmed);
  const retake = receipt.status === "retake";
  const failed = receipt.status === "failed";
  const label = confirmed
    ? "확정됨"
    : retake
      ? "다시 촬영 필요"
      : failed
        ? "읽기 실패"
        : "수정 필요";
  return {
    id: String(receipt.id),
    type: "매입",
    issuedAt: receipt.date ?? receipt.created_at.slice(0, 10),
    supplierName: receipt.vendor ?? (retake ? "다시 촬영 필요" : "확인 필요"),
    supplierBusinessNumber: receipt.business_number ?? "",
    itemSummary: label + (confirmed && !includedInTotal ? " · 합계 제외" : ""),
    includedInTotal,
    supplyAmount: separated ? receipt.taxable_supply_amount ?? 0 : receipt.supply_amount ?? 0,
    amount: receipt.transaction_amount ?? receipt.amount,
    taxExemptAmount: receipt.tax_exempt_amount,
    paymentAmount: receipt.payment_amount,
    subtotalAmount: receipt.subtotal_amount,
    transactionAmount: receipt.transaction_amount,
    vatAmount: receipt.vat_amount ?? 0,
    isExempt: receipt.tax_exempt_amount != null && receipt.tax_exempt_amount > 0 && receipt.taxable_supply_amount === 0 && receipt.vat_amount === 0,
    status: failed || retake ? "failed" : "completed",
    amountMissing: receipt.transaction_amount == null && receipt.amount == null,
    supplyMissing: separated ? receipt.taxable_supply_amount == null : receipt.supply_amount == null,
    vatMissing: receipt.vat_amount === null || receipt.vat_amount === undefined,
  };
}

export function PurchaseStoragePage() {
  const navigate = useNavigate();
  const [receipts, setReceipts] = useState<Receipt[]>([]);
  const hasToken = Boolean(localStorage.getItem("access_token"));
  const [loading, setLoading] = useState(hasToken);
  const [error, setError] = useState(hasToken ? "" : "로그인 후 영수증을 확인할 수 있습니다.");

  const loadReceipts = useCallback(async () => {
    if (!localStorage.getItem("access_token")) {
      setError("로그인 후 영수증을 확인할 수 있습니다.");
      setLoading(false);
      return;
    }

    setLoading(true);
    setError("");
    try {
      const [data, transactions] = await Promise.all([listReceipts(), listTransactions()]);
      const canonical = new Set(transactions.filter(t => t.workflow_status !== "MERGED" && t.workflow_status !== "UNRESOLVED_ADJUSTMENT")
        .map(t => t.canonical_receipt_id).filter(id => id != null));
      setReceipts(data.map(receipt => toReceiptView(receipt, Boolean(receipt.confirmed)
        && (!receipt.transaction_id || canonical.has(receipt.id)))));
    } catch (requestError) {
      const message = isAxiosError(requestError)
        ? requestError.response?.data?.error?.message
        : undefined;
      setError(message ?? "영수증 목록을 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (hasToken) void loadReceipts();
  }, [hasToken, loadReceipts]);

  const totalAmount = receipts.reduce((sum, receipt) => sum + (receipt.includedInTotal ? receipt.amount ?? 0 : 0), 0);
  const doneCount = receipts.filter((receipt) => receipt.status === "completed").length;
  const failedCount = receipts.filter((receipt) => receipt.status === "failed").length;

  return (
    <StorageView
      variant="primary"
      title="매입 영수증 보관함"
      summaryEyebrow="OCR 확정 거래 · 중복 증빙 제외 · 연결된 반품 반영"
      summaryLabel="확인된 거래 총액"
      listLabel="증빙 내역"
      disablePdf
      receipts={receipts}
      totalAmount={totalAmount}
      onRefresh={loadReceipts}
      onSelectReceipt={(receipt) => navigate(`/receipts/${receipt.id}/edit`)}
      loading={loading}
      error={error}
      summaryRows={[
        { label: "OCR 완료", countText: `${doneCount}건` },
        { label: "OCR 실패", countText: `${failedCount}건` },
      ]}
    />
  );
}
