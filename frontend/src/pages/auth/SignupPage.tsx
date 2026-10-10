import { useRef, useState } from "react";
import { isAxiosError } from "axios";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "../../components/PageHeader";
import { checkEmailAvailability, register } from "../../api/auth";
import { verifyBusiness, type BusinessVerificationResponse } from "../../api/business";

const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const specialCharacterPattern = /[!@#$%^&*()_+\-=[\]{};':"\\|,.<>/?`~]/;

function normalizedBusinessNumber(value: string) {
  return value.replace(/[\s-]/g, "");
}

function formattedBusinessNumber(value: string) {
  const digits = value.replace(/\D/g, "").slice(0, 10);
  if (digits.length <= 3) return digits;
  if (digits.length <= 5) return `${digits.slice(0, 3)}-${digits.slice(3)}`;
  return `${digits.slice(0, 3)}-${digits.slice(3, 5)}-${digits.slice(5)}`;
}

function validBusinessNumber(value: string) {
  return /^[0-9\s-]+$/.test(value) && /^[0-9]{10}$/.test(normalizedBusinessNumber(value));
}

function businessError(error: unknown) {
  if (!isAxiosError(error)) return "사업자정보 조회에 실패했습니다. 잠시 후 다시 시도해 주세요.";
  if (!error.response) return "사업자정보 조회 서비스에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.";
  const code = error.response?.data?.error?.code;
  switch (code) {
    case "VALIDATION_ERROR":
      return "사업자등록번호는 숫자 10자리로 입력해 주세요.";
    case "BUSINESS_NOT_REGISTERED":
      return "국세청에 등록된 사업자정보를 찾을 수 없습니다.";
    case "BUSINESS_API_TIMEOUT":
      return "국세청 조회 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.";
    case "BUSINESS_API_NOT_CONFIGURED":
    case "BUSINESS_API_AUTH_ERROR":
    case "BUSINESS_API_QUOTA_EXCEEDED":
      return "사업자정보 조회 서비스를 현재 이용할 수 없습니다. 잠시 후 다시 시도해 주세요.";
    default:
      return "사업자정보 조회에 실패했습니다. 잠시 후 다시 시도해 주세요.";
  }
}

function PasswordRequirement({ met, children }: { met: boolean; children: string }) {
  return (
    <li style={{ color: met ? "var(--color-primary)" : "var(--color-muted, #718096)", display: "flex", gap: 8, alignItems: "center" }}>
      <span aria-hidden="true">{met ? "✓" : "○"}</span>
      <span>{children}</span>
    </li>
  );
}

export function SignupPage() {
  const navigate = useNavigate();
  const verificationRun = useRef(0);
  const emailAvailabilityRun = useRef(0);
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [name, setName] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [businessNumber, setBusinessNumber] = useState("");
  const [verification, setVerification] = useState<BusinessVerificationResponse | null>(null);
  const [isVerifying, setIsVerifying] = useState(false);
  const [verificationError, setVerificationError] = useState("");
  const [email, setEmail] = useState("");
  const [emailAvailability, setEmailAvailability] = useState<"available" | "taken" | null>(null);
  const [emailCheckError, setEmailCheckError] = useState("");
  const [isCheckingEmail, setIsCheckingEmail] = useState(false);
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showPasswordConfirmation, setShowPasswordConfirmation] = useState(false);
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [privacyAccepted, setPrivacyAccepted] = useState(false);
  const [marketingAccepted, setMarketingAccepted] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const businessVerified = verification?.verified === true
    && verification.business_number === normalizedBusinessNumber(businessNumber);
  const passwordRequirements = [
    { label: "8자 이상", met: [...password].length >= 8 },
    { label: "영문 포함", met: /[A-Za-z]/.test(password) },
    { label: "숫자 포함", met: /[0-9]/.test(password) },
    { label: "특수문자 포함", met: specialCharacterPattern.test(password) },
  ];
  const passwordRulesMet = passwordRequirements.every((requirement) => requirement.met);
  const passwordTooLong = new TextEncoder().encode(password).length > 72;
  const passwordValid = passwordRulesMet && !passwordTooLong;
  const accountStepValid = emailPattern.test(email.trim())
    && emailAvailability === "available"
    && passwordValid
    && passwordConfirmation === password
    && !isCheckingEmail;
  const businessStepValid = name.trim().length > 0
    && businessName.trim().length > 0
    && validBusinessNumber(businessNumber)
    && businessVerified
    && !isVerifying;
  const canSubmit = accountStepValid && businessStepValid && termsAccepted && privacyAccepted && !isSubmitting;

  function handleBusinessNumberChange(value: string) {
    verificationRun.current += 1;
    setBusinessNumber(formattedBusinessNumber(value));
    setVerification(null);
    setVerificationError("");
    setIsVerifying(false);
  }

  function handleEmailChange(value: string) {
    emailAvailabilityRun.current += 1;
    setEmail(value);
    setEmailAvailability(null);
    setEmailCheckError("");
    setIsCheckingEmail(false);
  }

  async function handleCheckEmailAvailability() {
    const normalizedEmail = email.trim();
    if (!emailPattern.test(normalizedEmail)) return;
    const run = ++emailAvailabilityRun.current;
    setEmailAvailability(null);
    setEmailCheckError("");
    setIsCheckingEmail(true);
    try {
      const result = await checkEmailAvailability(normalizedEmail);
      if (run !== emailAvailabilityRun.current) return;
      setEmailAvailability(result.available ? "available" : "taken");
    } catch {
      if (run === emailAvailabilityRun.current) setEmailCheckError("이메일 사용 여부를 확인하지 못했습니다. 잠시 후 다시 시도해 주세요.");
    } finally {
      if (run === emailAvailabilityRun.current) setIsCheckingEmail(false);
    }
  }

  async function handleVerifyBusiness() {
    if (!validBusinessNumber(businessNumber)) {
      setVerificationError("사업자등록번호는 숫자 10자리로 입력해 주세요.");
      return;
    }
    const run = ++verificationRun.current;
    setVerification(null);
    setVerificationError("");
    setIsVerifying(true);
    try {
      const result = await verifyBusiness(normalizedBusinessNumber(businessNumber));
      if (run !== verificationRun.current) return;
      if (!result.verified || result.business_number !== normalizedBusinessNumber(businessNumber)) {
        setVerificationError("사업자정보 조회 결과를 확인할 수 없습니다. 다시 시도해 주세요.");
        return;
      }
      setVerification(result);
    } catch (requestError) {
      if (run === verificationRun.current) setVerificationError(businessError(requestError));
    } finally {
      if (run === verificationRun.current) setIsVerifying(false);
    }
  }

  async function handleSignup() {
    if (!canSubmit) return;
    setError("");
    setIsSubmitting(true);
    try {
      await register({
        email: email.trim(),
        password,
        name: name.trim(),
        business_name: businessName.trim(),
        business_number: normalizedBusinessNumber(businessNumber),
        terms_accepted: termsAccepted,
        privacy_accepted: privacyAccepted,
        marketing_accepted: marketingAccepted,
      });
      // Registration creates the account; the user signs in explicitly afterward.
      navigate("/login", { state: { signupEmail: email.trim(), signupComplete: true } });
    } catch (requestError) {
      const code = isAxiosError(requestError) ? requestError.response?.data?.error?.code : undefined;
      if (code === "EMAIL_ALREADY_EXISTS") {
        setEmailAvailability("taken");
        setStep(1);
        setError("이미 가입된 이메일입니다. 로그인해 주세요.");
      } else if (typeof code === "string" && code.startsWith("BUSINESS_")) {
        setVerification(null);
        setVerificationError(businessError(requestError));
        setError("사업자정보를 다시 확인해 주세요.");
        setStep(2);
      } else {
        setError("회원가입에 실패했습니다. 입력 내용을 확인하고 다시 시도해 주세요.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  function nextStep() {
    setError("");
    if (step === 1 && accountStepValid) setStep(2);
    else if (step === 2 && businessStepValid) setStep(3);
  }

  return (
    <div className="page">
      <PageHeader title="사업자 회원가입" onBack={() => step === 1 ? navigate("/login") : setStep((step - 1) as 1 | 2)} />
      <div className="page__body">
        <div style={{ display: "flex", justifyContent: "space-between", margin: "8px 0 20px", fontSize: 13, color: "var(--color-primary)" }}>
          <span>{step} / 3</span>
          <span>{step === 1 ? "계정 정보 입력" : step === 2 ? "사업자번호 확인" : "약관 동의"}</span>
        </div>

        {step === 1 && <>
          <div style={{ fontSize: 22, fontWeight: 800, lineHeight: 1.35, marginBottom: 20 }}>
            부가가치세 신고,<br />TAX-AI와 시작해 보세요
          </div>
          <div className="form-field">
            <label className="form-field__label" htmlFor="signup-email">이메일</label>
            <div className="form-field__input-row">
              <input id="signup-email" className="input" type="email" autoComplete="email" value={email} onChange={(e) => handleEmailChange(e.target.value)} />
              <button type="button" className="btn btn--secondary btn--sm" style={{ width: 104, flexShrink: 0 }} onClick={handleCheckEmailAvailability} disabled={!emailPattern.test(email.trim()) || isCheckingEmail}>
                {isCheckingEmail ? "확인 중..." : "중복 확인"}
              </button>
            </div>
            {emailAvailability === "available" && <div className="form-field__hint" role="status">사용할 수 있는 이메일입니다.</div>}
            {emailAvailability === "taken" && <div className="form-field__hint form-field__hint--error" role="alert">이미 가입된 메일입니다. 로그인해 주세요.</div>}
            {emailCheckError && <div className="form-field__hint form-field__hint--error" role="alert">{emailCheckError}</div>}
          </div>
          <div className="form-field">
            <label className="form-field__label" htmlFor="signup-password">비밀번호</label>
            <div className="form-field__input-row">
              <input id="signup-password" className="input" type={showPassword ? "text" : "password"} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
              <button type="button" className="btn btn--secondary btn--sm" style={{ width: 72, flexShrink: 0 }} onClick={() => setShowPassword((shown) => !shown)} aria-label={showPassword ? "비밀번호 숨기기" : "비밀번호 보기"}>{showPassword ? "숨기기" : "보기"}</button>
            </div>
            {password.length > 0 && (passwordTooLong
              ? <div className="form-field__hint form-field__hint--error" role="alert">비밀번호가 너무 깁니다. 더 짧게 입력해 주세요.</div>
              : passwordRulesMet
                ? <div className="form-field__hint" role="status">안전한 비밀번호예요.</div>
              : <ul aria-label="비밀번호 생성 조건" style={{ listStyle: "none", padding: 0, margin: "8px 0 0", display: "grid", gap: 5, fontSize: 13 }}>
                {passwordRequirements.map((requirement) => <PasswordRequirement key={requirement.label} met={requirement.met}>{requirement.label}</PasswordRequirement>)}
              </ul>)}
          </div>
          <div className="form-field">
            <label className="form-field__label" htmlFor="signup-password-confirmation">비밀번호 확인</label>
            <div className="form-field__input-row">
              <input id="signup-password-confirmation" className="input" type={showPasswordConfirmation ? "text" : "password"} autoComplete="new-password" value={passwordConfirmation} onChange={(e) => setPasswordConfirmation(e.target.value)} />
              <button type="button" className="btn btn--secondary btn--sm" style={{ width: 72, flexShrink: 0 }} onClick={() => setShowPasswordConfirmation((shown) => !shown)} aria-label={showPasswordConfirmation ? "비밀번호 확인 숨기기" : "비밀번호 확인 보기"}>{showPasswordConfirmation ? "숨기기" : "보기"}</button>
            </div>
            {passwordConfirmation && passwordConfirmation !== password && <div className="form-field__hint form-field__hint--error" role="alert">비밀번호가 일치하지 않습니다.</div>}
          </div>
          <button className="btn btn--primary" onClick={nextStep} disabled={!accountStepValid}>다음</button>
          <div className="muted" style={{ marginTop: 18, textAlign: "center", fontSize: 13 }}>이미 계정이 있으신가요? <button className="btn btn--ghost" style={{ padding: 4 }} onClick={() => navigate("/login")}>로그인하기</button></div>
        </>}

        {step === 2 && <>
          <div style={{ fontSize: 22, fontWeight: 800, margin: "8px 0" }}>사업자번호 확인</div>
          <div className="muted" style={{ marginBottom: 20, fontSize: 13 }}>가입에 필요한 사업자 기본 정보를 입력하고 국세청 상태를 확인합니다.</div>
          <div className="form-field">
            <label className="form-field__label" htmlFor="signup-name">대표자 이름</label>
            <input id="signup-name" className="input" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="form-field">
            <label className="form-field__label" htmlFor="signup-business-name">상호명</label>
            <input id="signup-business-name" className="input" autoComplete="organization" value={businessName} onChange={(e) => setBusinessName(e.target.value)} />
            <div className="form-field__hint">상호명은 직접 입력한 정보이며 국세청 상태조회로 확인되지 않습니다.</div>
          </div>
          <div className="form-field">
            <label className="form-field__label" htmlFor="signup-business-number">사업자등록번호</label>
            <div className="form-field__input-row">
              <input id="signup-business-number" className="input" inputMode="numeric" autoComplete="off" value={businessNumber} onChange={(e) => handleBusinessNumberChange(e.target.value)} />
              <button className="btn btn--secondary btn--sm" style={{ width: 110, flexShrink: 0 }} onClick={handleVerifyBusiness} disabled={isVerifying || !validBusinessNumber(businessNumber)}>{isVerifying ? "조회 중..." : "검증하기"}</button>
            </div>
            {businessNumber && !validBusinessNumber(businessNumber) && <div className="form-field__hint form-field__hint--error">사업자등록번호는 숫자 10자리로 입력해 주세요.</div>}
            {verificationError && <div className="form-field__hint form-field__hint--error" role="alert">{verificationError}</div>}
            {businessVerified && verification && <div className="form-field__hint" role="status">국세청 상태조회 완료 · {verification.business_status} · {verification.tax_type}{verification.end_date && ` · 폐업일자 ${verification.end_date}`}</div>}
          </div>
          {businessVerified && verification?.business_status_code === "02" && <div className="banner banner--warning" style={{ marginBottom: 16 }} role="status">현재 휴업 상태로 조회됩니다. 가입은 가능하지만 사업자 상태가 이후 세무 검토에 참고됩니다.</div>}
          {businessVerified && verification?.business_status_code === "03" && <div className="banner banner--error" style={{ marginBottom: 16 }} role="status">현재 폐업 상태로 조회됩니다. 가입은 가능하지만 사업자 상태가 이후 세무 검토에 참고됩니다.</div>}
          <button className="btn btn--primary" onClick={nextStep} disabled={!businessStepValid}>다음</button>
        </>}

        {step === 3 && <>
          <div style={{ fontSize: 22, fontWeight: 800, margin: "8px 0" }}>약관 동의</div>
          <div className="muted" style={{ marginBottom: 20, fontSize: 13 }}>필수 항목에 동의해야 가입할 수 있습니다.</div>
          <label style={{ display: "flex", gap: 10, alignItems: "center", padding: "16px 0", borderBottom: "1px solid var(--color-border, #e5e7eb)" }}>
            <input type="checkbox" checked={termsAccepted} onChange={(e) => setTermsAccepted(e.target.checked)} />
            <span>[필수] 서비스 이용약관에 동의합니다.</span>
          </label>
          <label style={{ display: "flex", gap: 10, alignItems: "center", padding: "16px 0", borderBottom: "1px solid var(--color-border, #e5e7eb)" }}>
            <input type="checkbox" checked={privacyAccepted} onChange={(e) => setPrivacyAccepted(e.target.checked)} />
            <span>[필수] 개인정보 처리방침에 동의합니다.</span>
          </label>
          <label style={{ display: "flex", gap: 10, alignItems: "center", padding: "16px 0 24px" }}>
            <input type="checkbox" checked={marketingAccepted} onChange={(e) => setMarketingAccepted(e.target.checked)} />
            <span>[선택] 혜택 및 소식 안내를 받겠습니다.</span>
          </label>
          {error && <div className="banner banner--error" style={{ margin: "0 0 16px" }} role="alert">{error}</div>}
          <button className="btn btn--primary" onClick={handleSignup} disabled={!canSubmit}>{isSubmitting ? "가입 처리 중..." : "가입 완료"}</button>
        </>}
      </div>
    </div>
  );
}
