import { useState, type FormEvent } from "react";
import { isAxiosError } from "axios";
import { Link, useLocation } from "react-router-dom";
import { requestPasswordReset, resetPassword } from "../../api/auth";
import { PageHeader } from "../../components/PageHeader";
import { Icon } from "../../components/Icon";

export function PasswordResetPage() {
  const location = useLocation();
  const isReset = location.pathname === "/reset-password";
  const token = new URLSearchParams(location.hash.slice(1)).get("token") ?? "";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault(); if (busy) return; setError("");
    if (isReset && (!token || password !== confirmation || !/[A-Za-z]/.test(password) || !/[0-9]/.test(password) || !/[^A-Za-z0-9\s]/.test(password) || password.length < 8 || new TextEncoder().encode(password).length > 72)) {
      setError("유효한 링크에서 영문·숫자·특수문자를 포함한 8자 이상 비밀번호를 동일하게 입력해 주세요."); return;
    }
    setBusy(true);
    try {
      const result = isReset ? await resetPassword(token, password) : await requestPasswordReset(email.trim());
      setMessage(result.message);
      if (isReset) { localStorage.removeItem("access_token"); setPassword(""); setConfirmation(""); }
    } catch (cause) {
      setError(isAxiosError(cause) ? cause.response?.data?.error?.message ?? "요청을 처리하지 못했습니다. 다시 시도해 주세요." : "요청을 처리하지 못했습니다.");
    } finally { setBusy(false); }
  }
  return <div className="page qa-page"><PageHeader title={isReset ? "새 비밀번호 설정" : "비밀번호 찾기"} showMenu={false}/><main className="page__body">
    <h1 className="screen-title">{isReset ? "새 비밀번호를 입력해 주세요" : "가입한 이메일을 입력해 주세요"}</h1>
    <p className="muted">{isReset ? "변경 후 모든 기기에서 다시 로그인해야 합니다." : "비밀번호 재설정 링크를 이메일로 보내드립니다. 링크는 20분간 유효합니다."}</p>
    {error && <p className="banner banner--error" role="alert">{error}</p>}
    {message ? <><p className="banner banner--info" role="status">{message}</p><Link className="btn btn--primary" to="/login">로그인으로 이동</Link>{!isReset && <button className="btn btn--ghost" onClick={()=>setMessage("")}>이메일 다시 입력</button>}</> : <form onSubmit={submit}>
      {isReset ? <>
        <label className="form-field"><span className="form-field__label">새 비밀번호</span><div className="password-field"><input className="input" type={visible ? "text" : "password"} autoComplete="new-password" value={password} onChange={e=>setPassword(e.target.value)} required minLength={8}/><button type="button" aria-label={visible ? "비밀번호 숨기기" : "비밀번호 보기"} onClick={()=>setVisible(!visible)}><Icon name={visible ? "eyeOff" : "eye"}/></button></div></label>
        <label className="form-field"><span className="form-field__label">새 비밀번호 확인</span><input className="input" type={visible ? "text" : "password"} autoComplete="new-password" value={confirmation} onChange={e=>setConfirmation(e.target.value)} required/></label>
        {!token && <p className="banner banner--warning">유효한 링크가 없습니다. <Link to="/forgot-password">재설정 메일을 요청해 주세요.</Link></p>}
      </> : <label className="form-field"><span className="form-field__label">이메일</span><input className="input" type="email" autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)} required/></label>}
      <button className="btn btn--primary" disabled={busy || (isReset && !token)}>{busy ? "처리 중…" : isReset ? "비밀번호 변경" : "재설정 메일 보내기"}</button>
    </form>}
  </main></div>;
}
