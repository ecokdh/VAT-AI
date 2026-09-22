interface SummaryCardProps {
  variant?: "primary" | "sales";
  eyebrow: string;
  label: string;
  amount: string;
  rows?: { label: string; value: string }[];
}

export function SummaryCard({ variant = "primary", eyebrow, label, amount, rows }: SummaryCardProps) {
  return (
    <div className={`summary-card summary-card--${variant}`}>
      <div className="summary-card__eyebrow">{eyebrow}</div>
      <div className="summary-card__label">{label}</div>
      <div className="summary-card__amount">{amount}</div>
      {rows && rows.length > 0 && (
        <>
          <hr className="summary-card__divider" />
          {rows.map((row) => (
            <div className="summary-card__row" key={row.label}>
              <span>{row.label}</span>
              <span>{row.value}</span>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
