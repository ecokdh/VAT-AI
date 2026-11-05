import { useEffect, useRef, useState } from "react";
import { isAxiosError } from "axios";
import { useLocation, useNavigate, Link } from "react-router-dom";
import { login } from "../../api/auth";
import { Icon } from "../../components/Icon";
import { BrandMark, BrandWordmark } from "../../components/BrandMark";
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
      <div className="login-orbs" aria-hidden="true"><span /><span /><span /><span /></div>
      {showLoading && <LoginLoadingScreen />}
      <div className="page__body">
        <div className="auth-intro">
          <div className="login-logo"><BrandMark /></div>
          <h1 className="auth-title"><BrandWordmark className="login-wordmark" /><span className="login-sr-only">VAT-AI</span></h1>
          <p className="auth-description">소상공인을 위한 스마트 부가가치세 비서</p>
        </div>

        <div className="form-field">
          <label className="form-field__label login-sr-only" htmlFor="login-email">대표자 이메일</label>
          <div className="login-field"><Icon name="user" /><input id="login-email" className="input" type="email" autoComplete="username" placeholder="대표자 이메일" value={email} onChange={(e) => setEmail(e.target.value)} /></div>
        </div>
        <div className="form-field">
          <label className="form-field__label login-sr-only" htmlFor="login-password">비밀번호</label>
          <div className="password-field login-field"><Icon name="lock" /><input id="login-password" ref={passwordInput} className="input" type={showPassword ? "text" : "password"} autoComplete="current-password" placeholder="비밀번호" value={password} onChange={(e) => setPassword(e.target.value)} /><button type="button" aria-label={showPassword ? "비밀번호 숨기기" : "비밀번호 보기"} aria-pressed={showPassword} onClick={() => setShowPassword(!showPassword)}><Icon name={showPassword ? "eyeOff" : "eye"} /></button></div>
        </div>

        {routeState?.signupComplete && <div className="banner" style={{ marginBottom: 16 }} role="status">가입이 완료되었습니다. 이메일과 비밀번호로 로그인해 주세요.</div>}

        <div className="auth-preferences">
          <label>
            <input type="checkbox" checked={rememberEmail} onChange={(e) => setRememberEmail(e.target.checked)} />
            이메일 저장
          </label>
          <Link className="text-link" to="/forgot-password">비밀번호를 잊으셨나요?</Link>
        </div>

        {error && (
          <div className="banner banner--error" style={{ marginBottom: 20 }}>
            <Icon name="info" />
            <div>{error}</div>
          </div>
        )}

        <div className="stack-gap-sm">
          <button className="btn btn--primary login-submit" onClick={handleLogin} disabled={isSubmitting}>
            {isSubmitting ? "로그인 중..." : "로그인"}
            <span className="login-submit__arrow"><Icon name="arrowRight" /></span>
          </button>
          <Link to="/signup" className="btn btn--ghost">
            회원가입 하기
          </Link>
        </div>
      </div>
    </div>
  );
}
