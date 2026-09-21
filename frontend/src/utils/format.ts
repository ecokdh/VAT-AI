export function formatWon(amount: number): string {
  return `${amount.toLocaleString("ko-KR")}원`;
}

export function formatWonSpaced(amount: number): string {
  return `${amount.toLocaleString("ko-KR")} 원`;
}

export function formatDate(iso: string): string {
  return iso.replaceAll("-", ".");
}
