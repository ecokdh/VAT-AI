import { useEffect, useRef, useState } from "react";
import { isAxiosError } from "axios";
import { useLocation, useNavigate, Link } from "react-router-dom";
import { PageHeader } from "../../components/PageHeader";
import { login } from "../../api/auth";
import { Icon } from "../../components/Icon";

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

  useEffect(() => {
    if (routeState?.signupComplete) passwordInput.current?.focus();
  }, [routeState?.signupComplete]);

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
    <div className="page auth-page">
      <PageHeader title="로그인" showBack={false} showMenu={false} />
      <div className="page__body">
        <div className="auth-intro">
          <img className="auth-logo" src="/vat-ai-logo.png" alt="VAT-AI 로고" width={320} height={252} />
          <h1 className="auth-title">VAT-AI</h1>
          <p className="auth-description">소상공인을 위한 스마트 부가가치세 비서</p>
        </div>

        <div className="form-field">
          <label className="form-field__label" htmlFor="login-email">대표자 이메일</label>
          <input id="login-email" className="input" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="form-field">
          <label className="form-field__label" htmlFor="login-password">비밀번호</label>
          <div className="password-field"><input id="login-password" ref={passwordInput} className="input" type={showPassword ? "text" : "password"} autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /><button type="button" aria-label={showPassword ? "비밀번호 숨기기" : "비밀번호 보기"} aria-pressed={showPassword} onClick={() => setShowPassword(!showPassword)}><Icon name={showPassword ? "eyeOff" : "eye"} /></button></div>
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
          <button className="btn btn--primary" onClick={handleLogin} disabled={isSubmitting}>
            {isSubmitting ? "로그인 중..." : "로그인"}
          </button>
          <Link to="/signup" className="btn btn--ghost">
            회원가입 하기
          </Link>
        </div>
      </div>
    </div>
  );
}
