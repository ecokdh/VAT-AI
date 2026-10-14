import { useLocation, useNavigate } from "react-router-dom";
import { parentRoute } from "../hooks/navigation";
import { AmountVisibilityToggle } from "./AmountVisibilityToggle";
import { AccountMenu } from "./AccountMenu";

interface PageHeaderProps {
  title: string;
  onBack?: () => void;
  showBack?: boolean;
  showAmountToggle?: boolean;
  showMenu?: boolean;
}

export function PageHeader({ title, onBack, showBack = true, showAmountToggle = false, showMenu = true }: PageHeaderProps) {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <header className="page-header">
      {showBack ? (
        <button className="icon-btn" aria-label="뒤로가기" onClick={onBack ?? (() => navigate(parentRoute(location.pathname, location.search)))}>
          ‹
        </button>
      ) : (
        <span className="icon-btn" />
      )}
      <span className="page-header__title">{title}</span>
      <div style={{ display: "flex", gap: 4 }}>
        {showAmountToggle && <AmountVisibilityToggle />}
        {showMenu && <AccountMenu />}
      </div>
    </header>
  );
}
