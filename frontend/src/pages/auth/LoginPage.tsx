import { useEffect, useRef, useState } from "react";
import { isAxiosError } from "axios";
import { useLocation, useNavigate, Link } from "react-router-dom";
import { login } from "../../api/auth";
import { Icon } from "../../components/Icon";
import { BrandMark } from "../../components/BrandMark";
import { LoginLoadingScreen } from "../../components/SplashScreen";
import "../../styles/login.css";

const LOADING_DELAY_MS = 600;

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const routeState = location.state as { signupEmail?: string; signupComplete?: boolean } | null;
  const passwordInput = useRef<HTMLInputElement>(null);
  const [email, setEmail] = useState(routeState?.signupEmail ?? localStorage.getItem("vat-ai-email") ?? "");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberEmail, setRememberEmail] = useState(true);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showLoading, setShowLoading] = useState(false);

  useEffect(() => {
    if (routeState?.signupComplete) passwordInput.current?.focus();
  }, [routeState?.signupComplete]);

  // 바로 실패하는 요청(비밀번호 오류 등)에는 대기 화면을 띄우지 않고, 응답이 늦어질 때만 보여준다.
  useEffect(() => {
    if (!isSubmitting) return;
    const timer = window.setTimeout(() => setShowLoading(true), LOADING_DELAY_MS);
    return () => { window.clearTimeout(timer); setShowLoading(false); };
  }, [isSubmitting]);

  async function handleLogin() {
    setError("");
    setIsSubmitting(true);
    try {
      const { access_token } = await login(email, password);
      localStorage.setItem("access_token", access_token);
      if (rememberEmail) localStorage.setItem("vat-ai-email", email.trim()); else localStorage.removeItem("vat-ai-email");
      navigate("/dashboard", {replace: true});
    } catch (e) {
      const message = isAxiosError(e) ? e.response?.data?.error?.message : undefined;
      setError(message ?? "로그인에 실패하였습니다.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="page auth-page login-page">
      {showLoading && <LoginLoadingScreen />}
      <div className="login-hero">
        <div className="login-logo"><BrandMark /></div>
        <h1 className="login-sr-only">VAT-AI</h1>
      </div>

      <div className="login-sheet">
        <h2 className="login-title">로그인</h2>

        <div className="login-field">
          <label htmlFor="login-email">대표자 이메일</label>
          <input id="login-email" type="email" autoComplete="username" placeholder="name@company.com" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="login-field">
          <label htmlFor="login-password">비밀번호</label>
          <div className="login-password">
            <input id="login-password" ref={passwordInput} type={showPassword ? "text" : "password"} autoComplete="current-password" placeholder="비밀번호 입력" value={password} onChange={(e) => setPassword(e.target.value)} />
            <button type="button" aria-label={showPassword ? "비밀번호 숨기기" : "비밀번호 보기"} aria-pressed={showPassword} onClick={() => setShowPassword(!showPassword)}><Icon name={showPassword ? "eyeOff" : "eye"} /></button>
          </div>
        </div>

        <div className="auth-preferences">
          <label>
            <input type="checkbox" checked={rememberEmail} onChange={(e) => setRememberEmail(e.target.checked)} />
            이메일 저장
          </label>
          <Link className="text-link" to="/forgot-password">비밀번호 찾기</Link>
        </div>

        {routeState?.signupComplete && <div className="banner login-notice" role="status">가입이 완료되었습니다. 이메일과 비밀번호로 로그인해 주세요.</div>}
        {error && (
          <div className="banner banner--error login-notice">
            <Icon name="info" />
            <div>{error}</div>
          </div>
        )}

        <div className="login-actions">
          <button className="btn login-submit" onClick={handleLogin} disabled={isSubmitting}>
            {isSubmitting ? "로그인 중..." : "로그인"}
          </button>
          <Link to="/signup" className="btn login-signup">회원가입</Link>
        </div>
      </div>
    </div>
  );
}
