import { Icon } from "./Icon";
import { avatarKey } from "../hooks/avatarStorage";
import { useRef } from "react";
import { Link } from "react-router-dom";
export function ProfileAvatar({ userId, src }: { userId?: string; src?: string | null }) {
  const image = src === undefined && userId ? localStorage.getItem(avatarKey(userId)) : src;
  return <span className="profile-avatar">{image ? <img src={image} alt="프로필 사진" /> : <Icon name="user" />}</span>;
}

export function ProfilePhoto({userId, src, showAccount = false}: {userId?: string; src?: string | null; showAccount?: boolean}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const image = src === undefined && userId ? localStorage.getItem(avatarKey(userId)) : src;
  return <><button className="profile-photo-trigger" aria-label="프로필 사진 확대" onClick={()=>dialog.current?.showModal()}><ProfileAvatar userId={userId} src={src}/></button>
    <dialog ref={dialog} className="profile-photo-dialog" aria-label="프로필 사진" onClick={e=>{if(e.target===e.currentTarget) dialog.current?.close();}}>
      <button className="icon-btn profile-photo-close" aria-label="확대 사진 닫기" onClick={()=>dialog.current?.close()} autoFocus>×</button>
      {image ? <img src={image} alt="확대된 프로필 사진"/> : <div className="profile-photo-empty"><Icon name="user" size={90}/><p>등록된 프로필 사진이 없습니다.</p></div>}
      {showAccount && <Link className="btn btn--secondary" to="/account" onClick={()=>dialog.current?.close()}>마이페이지</Link>}
    </dialog></>;
}
