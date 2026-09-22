import { useNavigate } from "react-router-dom";
import { AmountVisibilityToggle } from "./AmountVisibilityToggle";

interface PageHeaderProps {
  title: string;
  onBack?: () => void;
  showBack?: boolean;
  showAmountToggle?: boolean;
}

export function PageHeader({ title, onBack, showBack = true, showAmountToggle = false }: PageHeaderProps) {
  const navigate = useNavigate();

  return (
    <header className="page-header">
      {showBack ? (
        <button className="icon-btn" aria-label="뒤로가기" onClick={onBack ?? (() => navigate(-1))}>
          ‹
        </button>
      ) : (
        <span className="icon-btn" />
      )}
      <span className="page-header__title">{title}</span>
      <div style={{ display: "flex", gap: 4 }}>
        {showAmountToggle && <AmountVisibilityToggle />}
        <button className="icon-btn" aria-label="알림">
          🔔
        </button>
      </div>
    </header>
  );
}
