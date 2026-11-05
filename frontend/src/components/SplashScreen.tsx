import { useEffect, useState, type ReactNode } from "react";
import { BrandMark, BrandWordmark } from "./BrandMark";
import "../styles/splash.css";

const SPLASH_MS = 3000;

// 하늘색→파란색 배경 위에 로고를 띄우는 전체 화면. 첫 실행·로그인 대기에서 함께 쓴다.
export function BrandOverlay({ className, label, children }: { className?: string; label: string; children?: ReactNode }) {
  return (
    <div className={`splash ${className ?? ""}`} role="status" aria-label={label}>
      <div className="splash-brand">
        <BrandMark className="splash-mark" />
        <BrandWordmark className="splash-wordmark" />
        {children}
      </div>
    </div>
  );
}

// 앱 첫 실행 시 3초간 로고 화면을 띄운 뒤 사라진다. 아래 화면은 그동안 미리 렌더링된다.
export function SplashScreen() {
  const [visible, setVisible] = useState(true);
  useEffect(() => {
    const timer = window.setTimeout(() => setVisible(false), SPLASH_MS);
    return () => window.clearTimeout(timer);
  }, []);
  if (!visible) return null;

  return <BrandOverlay className="splash--intro" label="VAT-AI 로딩 중" />;
}

// 로그인 요청이 끝날 때까지 돌아가는 게이지와 함께 보여준다.
export function LoginLoadingScreen() {
  return (
    <BrandOverlay className="splash--loading" label="로그인 중">
      <div className="splash-spinner" aria-hidden="true" />
      <p className="splash-message">로그인 중...</p>
    </BrandOverlay>
  );
}
