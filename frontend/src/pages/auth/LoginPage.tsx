import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { PageHeader } from "../../components/PageHeader";
import { mockUser } from "../../mocks/user";

export function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState(mockUser.email);
  const [password, setPassword] = useState("");
  const [rememberEmail, setRememberEmail] = useState(true);

  function handleLogin() {
    // 스켈레톤 단계: 실제 인증 없이 목데이터 기반으로 대시보드로 이동
    navigate("/dashboard");
  }

  return (
    <div className="page">
      <PageHeader title="로그인" showBack={false} />
      <div className="page__body">
        <div style={{ textAlign: "center", padding: "24px 0 32px" }}>
          <div
            style={{
              width: 72,
              height: 72,
              borderRadius: 20,
              background: "var(--color-primary)",
              margin: "0 auto 16px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 32,
            }}
          >
            💼
          </div>
          <div style={{ fontSize: 26, fontWeight: 800 }}>TAX-AI</div>
          <div className="muted" style={{ marginTop: 6, fontSize: 14 }}>
            소상공인을 위한 스마트 부가가치세 비서
          </div>
        </div>

        <div className="form-field">
          <label className="form-field__label">대표자 이메일</label>
          <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="form-field">
          <label className="form-field__label">비밀번호</label>
          <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 13, margin: "4px 0 28px" }}>
          <label style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--color-primary)" }}>
            <input type="checkbox" checked={rememberEmail} onChange={(e) => setRememberEmail(e.target.checked)} />
            이메일 저장
          </label>
          <span className="muted">비밀번호를 잊으셨나요?</span>
        </div>

        <div className="stack-gap-sm">
          <button className="btn btn--primary" onClick={handleLogin}>
            로그인
          </button>
          <Link to="/signup" className="btn btn--ghost">
            회원가입 하기
          </Link>
        </div>
      </div>
    </div>
  );
}
