import { Icon } from "./Icon";
import { avatarKey } from "../hooks/avatarStorage";
export function ProfileAvatar({ userId, src }: { userId?: string; src?: string | null }) {
  const image = src === undefined && userId ? localStorage.getItem(avatarKey(userId)) : src;
  return <span className="profile-avatar">{image ? <img src={image} alt="프로필 사진" /> : <Icon name="user" />}</span>;
}
