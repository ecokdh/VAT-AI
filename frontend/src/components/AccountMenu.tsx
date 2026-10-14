import { useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Icon, type IconName } from "./Icon";

export function AccountMenu() {
  const dialog = useRef<HTMLDialogElement>(null);
  const navigate = useNavigate();
  const items: [string, string, string, IconName][] = [["매입 보관함", "매입 증빙·공제 분석", "/storage/purchase", "folder"], ["매출 보관함", "매출 증빙·거래 관리", "/storage/sales", "folder"], ["신고서 생성", "예상세액·미확인 항목", "/reports", "info"], ["마이페이지", "사업자정보·계정", "/account", "user"]];
  return <><button className="icon-btn" aria-label="메뉴 열기" onClick={() => dialog.current?.showModal()}><Icon name="menu" /></button>
    <dialog ref={dialog} className="navigation-dialog" aria-label="전체 메뉴"><div className="section-heading"><strong>VAT-AI</strong><button className="text-link" onClick={() => dialog.current?.close()} autoFocus>✕ 메뉴 닫기</button></div><nav className="action-list">{items.map(([title, detail, path, icon]) => <button key={path} onClick={() => { dialog.current?.close(); navigate(path); }}><Icon name={icon} /><span><strong>{title}</strong><small>{detail}</small></span><span>›</span></button>)}</nav></dialog></>;
}
