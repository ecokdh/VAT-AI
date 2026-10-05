import type { Receipt } from "../types";
import { formatDate } from "../utils/format";
import { useMaskedFormat } from "../hooks/useMaskedFormat";

interface ReceiptListRowProps {
  receipt: Receipt;
  onSelect?: (receipt: Receipt) => void;
}

export function ReceiptListRow({ receipt, onSelect }: ReceiptListRowProps) {
  const variant = receipt.type === "매입" ? "primary" : "sales";
  const fmt = useMaskedFormat();
  const displayAmount = receipt.amount ?? receipt.supplyAmount;
  const amountLabel = receipt.transactionAmount != null ? "거래 총액" : receipt.amount !== undefined ? "인식 금액" : "공급가액";
  const statusLabel = receipt.status === "failed" ? "OCR 실패" : receipt.isExempt ? "면세" : receipt.type;
  return (
    <div
      className="list-row"
      role={onSelect ? "button" : undefined}
      onClick={onSelect ? () => onSelect(receipt) : undefined}
      style={onSelect ? { cursor: "pointer" } : undefined}
    >
      <div className="list-row__top">
        <div>
          <div className="list-row__date">{formatDate(receipt.issuedAt)}</div>
          <div className="list-row__name">{receipt.supplierName}</div>
          <div className="list-row__memo">{receipt.itemSummary}</div>
        </div>
        <span className={`pill pill--${receipt.status === "failed" ? "muted" : variant}`}>{statusLabel}</span>
      </div>
      <div className="list-row__amounts">
        {receipt.subtotalAmount != null && <div className="list-row__amount-line"><span>할인 전 합계</span><span>{fmt.won(receipt.subtotalAmount)}</span></div>}
        {receipt.transactionAmount != null && <div className="list-row__amount-line"><span>과세 공급가액</span><span>{receipt.supplyMissing ? "확인 필요" : fmt.won(receipt.supplyAmount)}</span></div>}
        {receipt.taxExemptAmount != null && <div className="list-row__amount-line"><span>면세 금액</span><span>{fmt.won(receipt.taxExemptAmount)}</span></div>}
        {receipt.paymentAmount != null && <div className="list-row__amount-line"><span>결제금액</span><span>{fmt.won(receipt.paymentAmount)}</span></div>}
        <div className="list-row__amount-line">
          <span>{amountLabel}</span>
          <span>{receipt.amountMissing || receipt.amount === null ? "확인 필요" : fmt.won(displayAmount)}</span>
        </div>
        <div className="list-row__amount-line">
          <span>{receipt.isExempt ? "세액 (면세)" : "세액"}</span>
          <span style={{ color: variant === "primary" ? "var(--color-primary)" : "var(--color-sales-dark)" }}>
            {receipt.vatMissing ? "확인 필요" : fmt.won(receipt.vatAmount)}
          </span>
        </div>
      </div>
    </div>
  );
}
