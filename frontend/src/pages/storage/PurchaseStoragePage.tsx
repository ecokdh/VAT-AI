import { useCallback, useEffect, useState } from "react";
import { isAxiosError } from "axios";
import { listReceipts, type ReceiptApi } from "../../api/receipts";
import { StorageView } from "../../components/StorageView";
import type { Receipt } from "../../types";

function toReceiptView(receipt: ReceiptApi): Receipt {
  const failed = receipt.status === "failed";
  return {
    id: String(receipt.id),
    type: "매입",
    issuedAt: receipt.date ?? receipt.created_at.slice(0, 10),
    supplierName: receipt.vendor ?? "OCR 인식 실패",
    supplierBusinessNumber: "",
    itemSummary: failed ? "OCR 결과 없음" : "OCR 인식 완료",
    supplyAmount: receipt.amount ?? 0,
    amount: receipt.amount,
    vatAmount: 0,
    isExempt: false,
    status: failed ? "failed" : "completed",
  };
}

export function PurchaseStoragePage() {
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
      const data = await listReceipts();
      setReceipts(data.map(toReceiptView));
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

  const totalAmount = receipts.reduce((sum, receipt) => sum + (receipt.amount ?? 0), 0);
  const doneCount = receipts.filter((receipt) => receipt.status === "completed").length;
  const failedCount = receipts.filter((receipt) => receipt.status === "failed").length;

  return (
    <StorageView
      variant="primary"
      title="매입 영수증 보관함"
      receipts={receipts}
      totalAmount={totalAmount}
      onRefresh={loadReceipts}
      loading={loading}
      error={error}
      summaryRows={[
        { label: "OCR 완료", countText: `${doneCount}건` },
        { label: "OCR 실패", countText: `${failedCount}건` },
      ]}
    />
  );
}
