import { useAmountVisibility } from "../context/AmountVisibilityContext";
import { formatWon, formatWonSpaced } from "../utils/format";

const MASK = "••••••원";
const MASK_SPACED = "•••••• 원";

export function useMaskedFormat() {
  const { visible } = useAmountVisibility();
  return {
    won: (amount: number) => (visible ? formatWon(amount) : MASK),
    wonSpaced: (amount: number) => (visible ? formatWonSpaced(amount) : MASK_SPACED),
  };
}
