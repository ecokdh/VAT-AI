import { useMemo, useState } from "react";
import { PageHeader } from "./PageHeader";
import { SummaryCard } from "./SummaryCard";
import { FilterChips } from "./FilterChips";
import { ReceiptListRow } from "./ReceiptListRow";
import type { Receipt } from "../types";
import { useMaskedFormat } from "../hooks/useMaskedFormat";

export interface SummaryRowSpec {
  label: string;
  amount?: number;
  countText?: string;
}

interface StorageViewProps {
  variant: "primary" | "sales";
  title: string;
  receipts: Receipt[];
  totalAmount: number;
  summaryRows: SummaryRowSpec[];
  onRefresh?: () => void;
  loading?: boolean;
  error?: string;
}

const MONTHS = ["전체", "4월", "5월", "6월"];

function monthOf(iso: string): string {
  const m = Number(iso.split("-")[1]);
  return `${m}월`;
}

export function StorageView({
  variant,
  title,
  receipts,
  totalAmount,
  summaryRows,
  onRefresh,
  loading = false,
  error,
}: StorageViewProps) {
  const [activeMonth, setActiveMonth] = useState("전체");
  const fmt = useMaskedFormat();

  const filtered = useMemo(
    () => (activeMonth === "전체" ? receipts : receipts.filter((r) => monthOf(r.issuedAt) === activeMonth)),
    [receipts, activeMonth]
  );

  const ctaLabel = "합계표 생성 (PDF)";
  const ctaClass = variant === "primary" ? "btn--primary" : "btn--sales";
  const secondaryClass = variant === "primary" ? "btn--secondary" : "btn--secondary-sales";

  return (
    <div className="page">
      <PageHeader title={title} showAmountToggle />
      <div className="page__body">
        <SummaryCard
          variant={variant}
          eyebrow="2024년 1기 확정 · 과세기간 누적"
          label={`${variant === "primary" ? "매입" : "매출"}처별 세금계산서 합계금액`}
          amount={fmt.wonSpaced(totalAmount)}
          rows={summaryRows.map((row) => ({
            label: row.label,
            value:
              row.amount !== undefined
                ? row.countText
                  ? `${row.countText} · ${fmt.won(row.amount)}`
                  : fmt.won(row.amount)
                : (row.countText ?? ""),
          }))}
        />

        <div style={{ marginTop: 18, marginBottom: 12 }}>
          <FilterChips options={MONTHS} active={activeMonth} onChange={setActiveMonth} variant={variant} />
        </div>

        <div className="btn-row">
          <button className={`btn ${ctaClass}`}>{ctaLabel}</button>
          <button className={`btn ${secondaryClass}`} onClick={onRefresh} disabled={loading}>
            {loading ? "불러오는 중" : "새로고침"}
          </button>
        </div>

        {error && (
          <div className="banner banner--error" style={{ marginTop: 16 }}>
            <span>⚠️</span>
            <div>{error}</div>
          </div>
        )}

        <div className="section-title-row">
          <span className="section-title-row__title">거래 내역{activeMonth !== "전체" && ` (${activeMonth})`}</span>
          <span className="section-title-row__count">
            총 {filtered.length}건 · {fmt.won(filtered.reduce((sum, r) => sum + r.supplyAmount, 0))}
          </span>
        </div>

        <div>
          {filtered.map((receipt) => (
            <ReceiptListRow key={receipt.id} receipt={receipt} />
          ))}
          {loading && <div className="center-note">영수증을 불러오는 중입니다.</div>}
          {!loading && filtered.length === 0 && <div className="center-note">해당 월의 거래 내역이 없습니다.</div>}
        </div>
      </div>
    </div>
  );
}
