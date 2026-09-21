import type { Receipt } from "../types";
import { formatDate } from "../utils/format";
import { useMaskedFormat } from "../hooks/useMaskedFormat";

interface ReceiptListRowProps {
  receipt: Receipt;
}

export function ReceiptListRow({ receipt }: ReceiptListRowProps) {
  const variant = receipt.type === "매입" ? "primary" : "sales";
  const fmt = useMaskedFormat();
  return (
    <div className="list-row">
      <div className="list-row__top">
        <div>
          <div className="list-row__date">{formatDate(receipt.issuedAt)}</div>
          <div className="list-row__name">{receipt.supplierName}</div>
          <div className="list-row__memo">{receipt.itemSummary}</div>
        </div>
        <span className={`pill pill--${variant}`}>{receipt.isExempt ? "면세" : receipt.type}</span>
      </div>
      <div className="list-row__amounts">
        <div className="list-row__amount-line">
          <span>공급가액</span>
          <span>{fmt.won(receipt.supplyAmount)}</span>
        </div>
        <div className="list-row__amount-line">
          <span>{receipt.isExempt ? "세액 (면세)" : "세액"}</span>
          <span style={{ color: variant === "primary" ? "var(--color-primary)" : "var(--color-sales-dark)" }}>
            {fmt.won(receipt.vatAmount)}
          </span>
        </div>
      </div>
    </div>
  );
}
