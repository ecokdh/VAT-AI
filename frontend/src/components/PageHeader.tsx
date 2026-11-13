import { useLocation, useNavigate } from "react-router-dom";
import { parentRoute } from "../hooks/navigation";

interface PageHeaderProps {
  title: string;
  onBack?: () => void;
  showBack?: boolean;
}

export function PageHeader({ title, onBack, showBack = true }: PageHeaderProps) {
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
      <span className="icon-btn" aria-hidden="true" />
    </header>
  );
}
