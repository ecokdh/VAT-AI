import { useCallback, useEffect, useState } from "react";
import { isAxiosError } from "axios";
import { listReceipts, type ReceiptApi } from "../../api/receipts";
import { StorageView } from "../../components/StorageView";
import type { Receipt } from "../../types";

function toReceiptView(receipt: ReceiptApi): Receipt {
  const failed = receipt.status === "failed";
  const unsupported = receipt.status === "unsupported";
  const retake = receipt.status === "retake";
  const needsEdit = receipt.status === "needs_edit";

  let status: Receipt["status"] = "completed";
  let fallbackName = "인식 완료";
  let summary = "OCR 인식 완료";

  if (failed) {
    status = "failed";
    fallbackName = "분석 실패";
    summary = "실행 오류";
  } else if (unsupported) {
    status = "unsupported";
    fallbackName = "미지원 문서";
    summary = "미지원 증빙";
  } else if (retake) {
    status = "retake";
    fallbackName = "재촬영 필요";
    summary = receipt.guide_message || "사진 재촬영";
  } else if (needsEdit) {
    status = "needs_edit";
    fallbackName = receipt.vendor ?? "확인 필요";
    summary = "직접 확인 필요";
  }

  return {
    id: String(receipt.id),
    type: "매입",
    issuedAt: receipt.date ?? receipt.created_at.slice(0, 10),
    supplierName: receipt.vendor ?? fallbackName,
    supplierBusinessNumber: "",
    itemSummary: summary,
    supplyAmount: receipt.amount ?? 0,
    amount: receipt.amount,
    vatAmount: 0,
    isExempt: false,
    status,
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
  const issueCount = receipts.filter((receipt) => receipt.status === "failed" || receipt.status === "unsupported" || receipt.status === "retake").length;

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
        { label: "인식 완료", countText: `${doneCount}건` },
        { label: "재촬영 · 안내", countText: `${issueCount}건` },
      ]}
    />
  );
}
