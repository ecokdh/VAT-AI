import { StorageView } from "../../components/StorageView";
import { purchaseReceipts, purchaseTotals } from "../../mocks/receipts";

export function PurchaseStoragePage() {
  return (
    <StorageView
      variant="primary"
      title="매입 영수증 보관함"
      receipts={purchaseReceipts}
      totalAmount={purchaseTotals.supplyAmount}
      summaryRows={[
        { label: "매입세액 합계", amount: purchaseTotals.vatAmount },
        { label: "이번 기간 매입 건수", countText: `${purchaseTotals.count}건` },
      ]}
    />
  );
}
