import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getMe, type AuthUser } from "../api/auth";
import { PageHeader } from "../components/PageHeader";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { ProfilePhoto } from "../components/ProfileAvatar";
import { avatarKey } from "../hooks/avatarStorage";
import "../styles/receipt-review.css";
import {BusinessProfileForm} from "../components/BusinessProfileForm";
import { TaxProfileForm } from "../components/TaxProfileForm";

export function AccountPage() {
  const navigate = useNavigate();
  const [user,setUser] = useState<AuthUser | null>(null);
  const [photo,setPhoto] = useState<string | null>(null);
  const [logoutOpen,setLogoutOpen] = useState(false);
  const [error,setError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  useEffect(()=>{getMe().then(account=>{setUser(account);setPhoto(localStorage.getItem(avatarKey(account.id)));}).catch(()=>setError("내 정보를 불러오지 못했습니다."));},[]);
  function upload(file?:File) {
    if(!file || !user) return;
    if(!["image/jpeg","image/png","image/webp"].includes(file.type) || file.size>2*1024*1024) {setError("2MB 이하 JPG·PNG·WebP 이미지를 선택해 주세요.");return;}
    const reader=new FileReader();
    reader.onload=()=>{try { const data=String(reader.result);localStorage.setItem(avatarKey(user.id),data);setPhoto(data);setError("");} catch {setError("사진을 저장하지 못했습니다. 더 작은 이미지를 선택해 주세요.");}};
    reader.onerror=()=>setError("사진을 읽지 못했습니다.");
    reader.readAsDataURL(file);
  }
  return <div className="page qa-page"><PageHeader title="마이페이지"/><main className="page__body">
    {error && <p className="banner banner--error" role="alert">{error}</p>}
    <section className="profile-card"><ProfilePhoto src={photo}/><div><h1>{user?.name ?? "내 계정"}</h1><p className="muted">{user?.email}</p><button className="text-link" onClick={()=>input.current?.click()}>프로필 사진 변경</button></div></section>
    <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={e=>upload(e.target.files?.[0])}/>
    <p className="footnote">프로필 사진은 현재 브라우저에 저장되며 홈에서도 표시됩니다.</p>
    <BusinessProfileForm/><h2 className="section-title">과세기간·신고 정보</h2><TaxProfileForm/>
    <h2 className="section-title">계정</h2><button className="btn btn--danger-outline" onClick={()=>setLogoutOpen(true)}>로그아웃</button>
    <ConfirmDialog open={logoutOpen} title="로그아웃하시겠어요?" confirmLabel="로그아웃" onCancel={()=>setLogoutOpen(false)} onConfirm={()=>{localStorage.removeItem("access_token");navigate("/login",{replace:true});}}>다시 이용하려면 이메일과 비밀번호로 로그인해 주세요.</ConfirmDialog>
  </main></div>;
}
export function AboutPage() {
  return <div className="page qa-page"><PageHeader title="서비스 정보"/><main className="page__body"><section className="card"><h1>VAT-AI</h1><p>증빙을 모으고 거래 내용을 확인해 부가가치세 신고를 준비합니다.</p><p className="muted">예상세액은 참고용이며 홈택스 자동 신고를 수행하지 않습니다.</p></section></main></div>;
}
