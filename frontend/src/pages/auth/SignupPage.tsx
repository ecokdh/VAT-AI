import { useRef, useState } from "react";
import { isAxiosError } from "axios";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "../../components/PageHeader";
import { Icon } from "../../components/Icon";
import { checkEmailAvailability, emptyFilingInfo, register, validIndustryCode, type BusinessFilingInfo } from "../../api/auth";
import { BusinessFilingFields } from "../../components/BusinessFilingFields";
import { verifyBusinessIdentity, type BusinessVerificationResponse } from "../../api/business";

import { TaxProfileFields, emptyTaxProfile } from "../../components/TaxProfileFields";
import type { TaxProfileInput } from "../../api/transactions";
import "../../styles/signup.css";

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
    case "BUSINESS_IDENTITY_MISMATCH":
      return "대표자명·상호명·사업자번호·개업일이 일치하지 않아요. 사업자등록증을 확인해 주세요.";
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

// 빨간 안내 문구는 문장마다 한 줄로 나눠 보여 준다.
function sentences(text: string) {
  return text.split(/(?<=[.?!])\s+/).map((line, i) => <span key={i} className="text-line">{line}</span>);
}

function PasswordRequirement({ met, children }: { met: boolean; children: string }) {
  return (
    <li className={met ? "is-met" : undefined}>
      <span aria-hidden="true">{met ? "✓" : "○"}</span> {children}
    </li>
  );
}

export function SignupPage() {
  const navigate = useNavigate();
  const verificationRun = useRef(0);
  const emailAvailabilityRun = useRef(0);
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [taxProfile, setTaxProfile] = useState<TaxProfileInput>({...emptyTaxProfile});
  function updateProfile<K extends keyof TaxProfileInput>(key: K, value: TaxProfileInput[K]) {
    if (key === "business_start_date") invalidateIdentity();
    setTaxProfile(current => ({...current, [key]:value, confirmed:false}));
  }
  const [name, setName] = useState("");
  const [nickname, setNickname] = useState("");
  const [verifiedIdentity, setVerifiedIdentity] = useState("");
  const [identityBusy, setIdentityBusy] = useState(false);
  const [identityError, setIdentityError] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [filingInfo, setFilingInfo] = useState<BusinessFilingInfo>(emptyFilingInfo);
  const [businessNumber, setBusinessNumber] = useState("");
  const [verification, setVerification] = useState<BusinessVerificationResponse | null>(null);
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
  const identityKey = JSON.stringify([normalizedBusinessNumber(businessNumber), name.trim(), businessName.trim(), taxProfile.business_start_date]);
  const identityVerified = businessVerified && verifiedIdentity === identityKey;
  const identityReady = validBusinessNumber(businessNumber) && !!name.trim() && !!businessName.trim() && !!taxProfile.business_start_date;
  const passwordRequirements = [
    { label: "8자 이상", met: [...password].length >= 8 },
    { label: "영문", met: /[A-Za-z]/.test(password) },
    { label: "숫자", met: /[0-9]/.test(password) },
    { label: "특수문자", met: specialCharacterPattern.test(password) },
  ];
  const passwordRulesMet = passwordRequirements.every((requirement) => requirement.met);
  const passwordTooLong = new TextEncoder().encode(password).length > 72;
  const passwordValid = passwordRulesMet && !passwordTooLong;
  const accountStepValid = emailPattern.test(email.trim())
    && nickname.trim().length >= 2 && nickname.trim().length <= 20
    && emailAvailability === "available"
    && passwordValid
    && passwordConfirmation === password
    && !isCheckingEmail;
  const businessStepValid = name.trim().length > 0
    && businessName.trim().length > 0
    && validBusinessNumber(businessNumber)
    && businessVerified
    && identityVerified
    && !identityBusy
    && !!taxProfile.entity_type && !!taxProfile.industry_category && !!taxProfile.business_start_date
    && validIndustryCode(filingInfo.industry_code)
    && taxProfile.taxable_sales_h1 != null && taxProfile.taxable_sales_h2 != null
    && (taxProfile.industry_category === "other" || !!taxProfile.industry_subtype)
    && (taxProfile.industry_category !== "manufacturing" || taxProfile.entity_type !== "corporation" || taxProfile.industry_subtype !== "other" || taxProfile.is_sme != null)
    && (verification?.tax_type_code !== "02" || taxProfile.simplified_industry_rate != null)
    && taxProfile.confirmed;
  const canSubmit = accountStepValid && businessStepValid && termsAccepted && privacyAccepted && !isSubmitting;

  function invalidateIdentity() {
    verificationRun.current += 1;
    setVerification(null);
    setVerifiedIdentity("");
    setIdentityError("");
    setIdentityBusy(false);
    setTaxProfile(current => ({...current, confirmed:false}));
  }

  function handleBusinessNumberChange(value: string) {
    invalidateIdentity();
    setBusinessNumber(formattedBusinessNumber(value));
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

  async function handleSignup() {
    if (!canSubmit) return;
    setError("");
    setIsSubmitting(true);
    try {
      await register({
        email: email.trim(),
        password,
        name: name.trim(),
        nickname: nickname.trim(),
        business_name: businessName.trim(),
        business_number: normalizedBusinessNumber(businessNumber),
        terms_accepted: termsAccepted,
        privacy_accepted: privacyAccepted,
        marketing_accepted: marketingAccepted,
        tax_profile: taxProfile,
        filing_info: filingInfo,
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
        setVerifiedIdentity("");
        setVerification(null);
        setIdentityError(businessError(requestError));
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

  async function handleVerifyIdentity() {
    if (!identityReady || !taxProfile.business_start_date || identityBusy) return;
    const run = ++verificationRun.current;
    setIdentityBusy(true);setIdentityError("");setVerifiedIdentity("");
    setVerification(null);
    try {
      const result = await verifyBusinessIdentity(normalizedBusinessNumber(businessNumber), name.trim(), taxProfile.business_start_date, businessName.trim());
      if (run !== verificationRun.current) return;
      if (!result.verified || result.business_number !== normalizedBusinessNumber(businessNumber)) {
        setIdentityError("사업자정보 조회 결과를 확인할 수 없습니다. 다시 시도해 주세요.");
        return;
      }
      setVerification(result);
      setVerifiedIdentity(identityKey);
    } catch (e) {if (run === verificationRun.current) setIdentityError(businessError(e));}
    finally {if (run === verificationRun.current) setIdentityBusy(false);}
  }

  return (
    <div className="page signup-page">
      <PageHeader title="사업자 회원가입" onBack={() => step === 1 ? navigate("/login") : setStep((step - 1) as 1 | 2)} />
      <div className="page__body">
        <div className="signup-progress" aria-hidden="true">{[1, 2, 3].map((n) => <span key={n} className={n <= step ? "is-on" : undefined} />)}</div>
        <div className="signup-pane" key={step}>
        <p className="signup-step">{step} / 3 · {step === 1 ? "계정 정보 입력" : step === 2 ? "사업자번호 확인" : "약관 동의"}</p>

        {step === 1 && <>
          <h1 className="signup-title">부가가치세 신고,<br />VAT-AI와 시작해 보세요</h1>
          <div className="form-field"><label className="form-field__label" htmlFor="signup-nickname">닉네임</label><input id="signup-nickname" className="input" autoComplete="nickname" maxLength={20} value={nickname} onChange={e=>setNickname(e.target.value)}/><p className="form-field__hint"><span className="text-line">홈 화면에 보일 이름이에요.</span><span className="text-line">2~20자로 입력하세요.</span></p></div>
          <div className="form-field">
            <label className="form-field__label" htmlFor="signup-email">이메일</label>
            <div className="form-field__input-row">
              <input id="signup-email" className="input" type="email" autoComplete="email" value={email} onChange={(e) => handleEmailChange(e.target.value)} />
              <button type="button" className="signup-inline-btn" onClick={handleCheckEmailAvailability} disabled={!emailPattern.test(email.trim()) || isCheckingEmail}>
                {isCheckingEmail ? "확인 중..." : "중복 확인"}
              </button>
            </div>
            {emailAvailability === "available" && <div className="form-field__hint" role="status">사용할 수 있는 이메일입니다.</div>}
            {emailAvailability === "taken" && <div className="form-field__hint form-field__hint--error" role="alert">{sentences("이미 가입된 메일입니다. 로그인해 주세요.")}</div>}
            {emailCheckError && <div className="form-field__hint form-field__hint--error" role="alert">{sentences(emailCheckError)}</div>}
          </div>
          <div className="form-field">
            <label className="form-field__label" htmlFor="signup-password">비밀번호</label>
            <div className="form-field__input-row">
              <input id="signup-password" className="input" type={showPassword ? "text" : "password"} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
              <button type="button" className="signup-eye" onClick={() => setShowPassword((shown) => !shown)} aria-label={showPassword ? "비밀번호 숨기기" : "비밀번호 보기"} aria-pressed={showPassword}><Icon name={showPassword ? "eyeOff" : "eye"} /></button>
            </div>
            {password.length > 0 && (passwordTooLong
              ? <div className="form-field__hint form-field__hint--error" role="alert">{sentences("비밀번호가 너무 깁니다. 더 짧게 입력해 주세요.")}</div>
              : passwordRulesMet
                ? <div className="form-field__hint" role="status">안전한 비밀번호예요.</div>
              : <ul className="signup-rules" aria-label="비밀번호 생성 조건">
                {passwordRequirements.map((requirement) => <PasswordRequirement key={requirement.label} met={requirement.met}>{requirement.label}</PasswordRequirement>)}
              </ul>)}
          </div>
          <div className="form-field">
            <label className="form-field__label" htmlFor="signup-password-confirmation">비밀번호 확인</label>
            <div className="form-field__input-row">
              <input id="signup-password-confirmation" className="input" type={showPasswordConfirmation ? "text" : "password"} autoComplete="new-password" value={passwordConfirmation} onChange={(e) => setPasswordConfirmation(e.target.value)} />
              <button type="button" className="signup-eye" onClick={() => setShowPasswordConfirmation((shown) => !shown)} aria-label={showPasswordConfirmation ? "비밀번호 확인 숨기기" : "비밀번호 확인 보기"} aria-pressed={showPasswordConfirmation}><Icon name={showPasswordConfirmation ? "eyeOff" : "eye"} /></button>
            </div>
            {passwordConfirmation && passwordConfirmation !== password && <div className="form-field__hint form-field__hint--error" role="alert">비밀번호가 일치하지 않습니다.</div>}
          </div>
          <div className="signup-cta"><button className="btn btn--primary" onClick={nextStep} disabled={!accountStepValid}>다음</button></div>
        </>}

        {step === 2 && <>
          <h1 className="signup-title">사업자번호 확인</h1>
          <p className="signup-sub"><span className="text-line">사업자 기본 정보를 입력해 주세요.</span><span className="text-line">국세청에서 사업자 상태를 확인해요.</span></p>
          <div className="form-field">
            <label className="form-field__label" htmlFor="signup-name">대표자 이름<span className="field-req" aria-hidden="true">*</span></label>
            <input id="signup-name" className="input" autoComplete="name" required value={name} onChange={(e) => { invalidateIdentity(); setName(e.target.value); }} />
          </div>
          <div className="form-field">
            <label className="form-field__label" htmlFor="signup-business-name">상호명<span className="field-req" aria-hidden="true">*</span></label>
            <input id="signup-business-name" className="input" autoComplete="organization" required value={businessName} onChange={(e) => { invalidateIdentity(); setBusinessName(e.target.value); }} />
            <div className="form-field__hint"><span className="text-line">사업자등록증에 적힌 상호를 입력하세요.</span><span className="text-line">가입 후에는 바꿀 수 없어요.</span></div>
          </div>
          <div className="form-field">
            <label className="form-field__label" htmlFor="signup-business-number">사업자등록번호<span className="field-req" aria-hidden="true">*</span></label>
            <input id="signup-business-number" className="input" inputMode="numeric" autoComplete="off" required value={businessNumber} onChange={(e) => handleBusinessNumberChange(e.target.value)} />
            {businessNumber && !validBusinessNumber(businessNumber) && <div className="form-field__hint form-field__hint--error">사업자등록번호는 숫자 10자리로 입력해 주세요.</div>}
          </div>
          <div className="form-field">
            <label className="form-field__label" htmlFor="signup-business-start">개업일<span className="field-req" aria-hidden="true">*</span></label>
            <input id="signup-business-start" className="input" type="date" required value={taxProfile.business_start_date ?? ""} onChange={e => updateProfile("business_start_date", e.target.value || null)} />
          </div>
          {/* 네 가지 정보로 국세청 진위확인(상태조회 포함)을 한 번에 하고, 통과하면 나머지 정보를 입력한다 */}
          <div className="identity-check">
            <p className="signup-note"><span className="text-line">대표자명·상호명·사업자번호·개업일을 대조해요.</span></p>
            <button type="button" className={`btn ${identityReady && !identityVerified ? "btn--primary" : "btn--secondary"}`} onClick={()=>void handleVerifyIdentity()} disabled={identityBusy || !identityReady || identityVerified}>{identityBusy ? "진위확인 중…" : identityVerified ? "대표자 진위확인 완료" : "대표자 진위확인"}</button>
            {identityError && <p className="form-field__hint form-field__hint--error" role="alert">{sentences(identityError)}</p>}
            {identityVerified && verification && <p className="form-field__hint" role="status"><span className="text-line">국세청 등록정보와 일치해요.</span><span className="text-line">{verification.business_status} · {verification.tax_type}{verification.end_date && ` · 폐업일자 ${verification.end_date}`}</span></p>}
          </div>
          {identityVerified && verification?.business_status_code === "02" && <div className="banner banner--warning" style={{ marginBottom: 16 }} role="status">현재 휴업 상태로 조회됩니다. 가입은 가능하지만 사업자 상태가 이후 세무 검토에 참고됩니다.</div>}
          {identityVerified && verification?.business_status_code === "03" && <div className="banner banner--error" style={{ marginBottom: 16 }} role="status">현재 폐업 상태로 조회됩니다. 가입은 가능하지만 사업자 상태가 이후 세무 검토에 참고됩니다.</div>}
          {identityVerified && <section className="signup-tax-profile"><h2 className="section-title">사업자·과세기간 정보</h2>
            <div className="signup-tax-type"><span>국세청 조회 과세유형</span><strong>{verification?.tax_type}</strong></div>
            <p className="signup-note"><span className="text-line">아래 정보를 확인하면 가입과 함께 저장돼요.</span></p>
            <TaxProfileFields taxProfile={taxProfile} taxType={verification?.tax_type_code === "02" ? "simplified" : "general"} updateProfile={updateProfile} showBusinessStartDate={false}/>
            <BusinessFilingFields signup value={filingInfo} onChange={(key, value) => setFilingInfo(current => ({ ...current, [key]: value }))} />
            <label className="check-row"><input type="checkbox" checked={taxProfile.confirmed} onChange={e=>setTaxProfile(current=>({...current,confirmed:e.target.checked}))}/>입력한 사업자 정보를 확인했습니다.</label>
          </section>}
          <div className="signup-cta"><button className="btn btn--primary" onClick={nextStep} disabled={!businessStepValid}>다음</button></div>
        </>}

        {step === 3 && <>
          <h1 className="signup-title">약관 동의</h1>
          <p className="signup-sub"><span className="text-line">필수 항목에 동의해야 가입할 수 있어요.</span></p>
          <div className="signup-terms">
            <label>
              <input type="checkbox" checked={termsAccepted} onChange={(e) => setTermsAccepted(e.target.checked)} />
              <span>[필수] 서비스 이용약관에 동의합니다.</span>
              <span className="signup-terms__arrow" aria-hidden="true">›</span>
            </label>
            <label>
              <input type="checkbox" checked={privacyAccepted} onChange={(e) => setPrivacyAccepted(e.target.checked)} />
              <span>[필수] 개인정보 처리방침에 동의합니다.</span>
              <span className="signup-terms__arrow" aria-hidden="true">›</span>
            </label>
            <label>
              <input type="checkbox" checked={marketingAccepted} onChange={(e) => setMarketingAccepted(e.target.checked)} />
              <span>[선택] 혜택 및 소식 안내를 받겠습니다.</span>
            </label>
          </div>
          {error && <div className="banner banner--error signup-error" role="alert">{sentences(error)}</div>}
          <div className="signup-cta"><button className="btn btn--primary" onClick={handleSignup} disabled={!canSubmit}>{isSubmitting ? "가입 처리 중..." : "가입 완료"}</button></div>
        </>}
        </div>
      </div>
    </div>
  );
}
