import { useAmountVisibility } from "../context/AmountVisibilityContext";
import { Icon } from "./Icon";

export function AmountVisibilityToggle() {
  const { visible, toggle } = useAmountVisibility();
  return (
    <button className="icon-btn" aria-label={visible ? "금액 숨기기" : "금액 보기"} onClick={toggle}>
      <Icon name={visible ? "eyeOff" : "eye"} />
    </button>
  );
}
