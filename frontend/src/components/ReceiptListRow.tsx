import type { Receipt } from "../types";
import { formatDate } from "../utils/format";
import { useMaskedFormat } from "../hooks/useMaskedFormat";

interface ReceiptListRowProps {
  receipt: Receipt;
}

export function ReceiptListRow({ receipt }: ReceiptListRowProps) {
  const variant = receipt.type === "매입" ? "primary" : "sales";
  const fmt = useMaskedFormat();
  const displayAmount = receipt.amount ?? receipt.supplyAmount;
  const amountLabel = receipt.amount !== undefined ? "인식 금액" : "공급가액";
  const statusLabel =
    receipt.status === "failed" ? "분석 실패" :
    receipt.status === "unsupported" ? "미지원 문서" :
    receipt.status === "retake" ? "재촬영 필요" :
    receipt.status === "needs_edit" ? "확인 필요" :
    receipt.isExempt ? "면세" : receipt.type;
  const pillVariant =
    (receipt.status === "failed" || receipt.status === "unsupported") ? "muted" :
    (receipt.status === "retake" || receipt.status === "needs_edit") ? "warning" : variant;
  return (
    <div className="list-row">
      <div className="list-row__top">
        <div>
          <div className="list-row__date">{formatDate(receipt.issuedAt)}</div>
          <div className="list-row__name">{receipt.supplierName}</div>
          <div className="list-row__memo">{receipt.itemSummary}</div>
        </div>
        <span className={`pill pill--${pillVariant}`}>{statusLabel}</span>
      </div>
      <div className="list-row__amounts">
        <div className="list-row__amount-line">
          <span>{amountLabel}</span>
          <span>{receipt.amount === null ? "인식되지 않음" : fmt.won(displayAmount)}</span>
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
