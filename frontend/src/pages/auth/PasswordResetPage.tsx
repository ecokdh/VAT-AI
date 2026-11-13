import { useEffect, useState, type FormEvent } from "react";
import { isAxiosError } from "axios";
import { Link, useLocation } from "react-router-dom";
import { requestPasswordReset, resetPassword, verifyPasswordResetCode } from "../../api/auth";
import { PageHeader } from "../../components/PageHeader";
import { Icon } from "../../components/Icon";
import { PASSWORD_RESET_PENDING_KEY, readPendingPasswordReset } from "../../hooks/passwordResetState";
import "../../styles/password-reset.css";

export function PasswordResetPage() {
  const location = useLocation();
  const legacyToken = new URLSearchParams(location.hash.slice(1)).get("token") ?? "";
  const [pending] = useState(() => {
    try { return readPendingPasswordReset(sessionStorage.getItem(PASSWORD_RESET_PENDING_KEY), Date.now()); }
    catch { return null; }
  });
  const [step, setStep] = useState<"email" | "code" | "password" | "done">(legacyToken ? "password" : pending ? "code" : "email");
  const [token, setToken] = useState(legacyToken);
  const [email, setEmail] = useState(pending?.email ?? "");
  const [requestId, setRequestId] = useState(pending?.requestId ?? "");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [resendAt, setResendAt] = useState(pending?.resendAt ?? 0);
  const [expiresAt, setExpiresAt] = useState(pending?.expiresAt ?? 0);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (step !== "code") return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [step]);
  const remaining = Math.max(0, Math.ceil((expiresAt - now) / 1000));
  const resendWait = Math.max(0, Math.ceil((resendAt - now) / 1000));
  useEffect(() => {
    try {
      if (step === "code") sessionStorage.setItem(PASSWORD_RESET_PENDING_KEY, JSON.stringify({ email: email.trim(), requestId, expiresAt, resendAt }));
      else sessionStorage.removeItem(PASSWORD_RESET_PENDING_KEY);
    } catch { /* A blocked storage must not prevent password recovery. */ }
  }, [step, email, requestId, expiresAt, resendAt]);

  async function sendCode() {
    const result = await requestPasswordReset(email.trim());
    const sentAt = Date.now();
    setNow(sentAt); setRequestId(result.request_id);
    setResendAt(sentAt + result.retry_after * 1000);
    setExpiresAt(sentAt + result.expires_in * 1000);
    setCode(""); setMessage(result.message); setStep("code");
  }
  function showError(cause: unknown) {
    setError(isAxiosError(cause) ? cause.response?.data?.error?.message ?? "요청을 처리하지 못했습니다. 다시 시도해 주세요." : "요청을 처리하지 못했습니다.");
  }
  async function resend() {
    if (busy || resendWait > 0) return;
    setError(""); setBusy(true);
    try { await sendCode(); } catch (cause) { showError(cause); } finally { setBusy(false); }
  }
  async function submit(event: FormEvent) {
    event.preventDefault(); if (busy) return; setError("");
    if (step === "password" && (password !== confirmation || !/[A-Za-z]/.test(password) || !/[0-9]/.test(password) || !/[^A-Za-z0-9\s]/.test(password) || password.length < 8 || new TextEncoder().encode(password).length > 72)) {
      setError("영문·숫자·특수문자를 포함한 8자 이상, 72바이트 이하 비밀번호를 동일하게 입력해 주세요."); return;
    }
    setBusy(true);
    try {
      if (step === "email") {
        await sendCode();
      } else if (step === "code") {
        const result = await verifyPasswordResetCode(requestId, code);
        setToken(result.token); setCode(""); setMessage(""); setStep("password");
      } else if (step === "password") {
        await resetPassword(token, password);
        localStorage.removeItem("access_token");
        setToken(""); setPassword(""); setConfirmation(""); setMessage(""); setStep("done");
      }
    } catch (cause) { showError(cause); } finally { setBusy(false); }
  }
  const isPassword = step === "password";
  return <div className="page qa-page reset-page"><PageHeader title={step === "done" ? "비밀번호 변경 완료" : isPassword ? "새 비밀번호 설정" : "비밀번호 찾기"}/><main className="page__body">
    {step !== "done" && <h1 className="screen-title">{isPassword ? "새 비밀번호를 입력해 주세요" : step === "code" ? "이메일 인증 코드를 입력해 주세요" : "가입한 이메일을 입력해 주세요"}</h1>}
    {(step === "email" || step === "code") && <p className="muted">{step === "code" ? `${email.trim()}로 보낸 6자리 코드를 입력해 주세요.` : "가입한 이메일로 6자리 인증 코드를 보내드립니다. 코드는 10분간 유효합니다."}</p>}
    {error && <p className="banner banner--error" role="alert">{error.split(/(?<=[.?!])\s+/).map((line, i) => <span key={i} className="text-line">{line}</span>)}</p>}
    {step === "code" && message && <p className="banner banner--info" role="status">{message}</p>}
    {step === "done" ? <Link className="btn btn--primary" to="/login">로그인 화면으로 이동</Link> : <form onSubmit={submit}>
      {isPassword ? <>
        <label className="form-field"><span className="form-field__label">새 비밀번호</span><div className="password-field"><input className="input" type={visible ? "text" : "password"} autoComplete="new-password" value={password} onChange={e=>setPassword(e.target.value)} required minLength={8}/><button type="button" aria-label={visible ? "비밀번호 숨기기" : "비밀번호 보기"} aria-pressed={visible} onClick={()=>setVisible(!visible)}><Icon name={visible ? "eyeOff" : "eye"}/></button></div></label>
        <label className="form-field"><span className="form-field__label">새 비밀번호 확인</span><input className="input" type={visible ? "text" : "password"} autoComplete="new-password" value={confirmation} onChange={e=>setConfirmation(e.target.value)} required/></label>
      </> : step === "code" ? <>
        <label className="form-field"><span className="form-field__label">인증 코드</span><input className="input" type="text" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} value={code} onChange={e=>setCode(e.target.value.replace(/[^0-9]/g, "").slice(0, 6))} required aria-describedby="reset-code-expiry"/></label>
        <p className="muted" id="reset-code-expiry">{remaining > 0 ? `남은 시간 ${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, "0")}` : "인증 코드가 만료되었습니다. 새 코드를 요청해 주세요."}</p>
      </> : <label className="form-field"><span className="form-field__label">이메일</span><input className="input" type="email" autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)} required/></label>}
      <div className="stack-gap-sm">
        <button className="btn btn--primary" disabled={busy || (step === "code" && (code.length !== 6 || remaining === 0))}>{busy ? "처리 중…" : isPassword ? "비밀번호 변경" : step === "code" ? "인증 코드 확인" : "인증 코드 보내기"}</button>
        {step === "code" && <button type="button" className="btn btn--ghost" disabled={busy || resendWait > 0} onClick={resend}>{resendWait > 0 ? `인증 코드 재발송 (${resendWait}초)` : "인증 코드 재발송"}</button>}
      </div>
    </form>}
  </main></div>;
}
