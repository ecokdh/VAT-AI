import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Icon } from "./Icon";

export function AccountMenu() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  return <div className="account-menu">
    <button className="icon-btn" aria-label="메뉴 열기" aria-expanded={open} onClick={() => setOpen(!open)}><Icon name="menu" /></button>
    {open && <>
      <button className="menu-backdrop" aria-label="메뉴 닫기" onClick={() => setOpen(false)} />
      <div className="account-menu__items" onKeyDown={(event) => { if (event.key === "Escape") setOpen(false); }}>
        <button onClick={() => { setOpen(false); navigate("/account"); }}><Icon name="user" />내 정보</button>
        <button onClick={() => { setOpen(false); navigate("/about"); }}><Icon name="info" />서비스 정보</button>
        <button onClick={() => { localStorage.removeItem("access_token"); navigate("/login", { replace: true }); }}><Icon name="logout" />로그아웃</button>
      </div>
    </>}
  </div>;
}
