import { StorageView } from "../../components/StorageView";
import { salesReceipts, salesTotals } from "../../mocks/receipts";

export function SalesStoragePage() {
  return (
    <StorageView
      variant="sales"
      title="매출 영수증 보관함"
      receipts={salesReceipts}
      totalAmount={salesTotals.supplyAmount}
      summaryRows={[
        { label: "누적 매출세액", amount: salesTotals.vatAmount },
        { label: "이번달 거래", countText: `${salesTotals.thisMonthCount}건`, amount: salesTotals.thisMonthSupplyAmount },
      ]}
    />
  );
}
