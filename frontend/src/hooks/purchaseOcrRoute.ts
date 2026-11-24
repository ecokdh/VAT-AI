export const purchaseOcrOptions = {
  qwen_ocr: { label: "짧고 선명해요", description: "품목이 몇 줄이고, 날짜와 합계가 바로 보여요." },
  qwen_photo_ocr: { label: "품목이 많고 글씨는 선명해요", description: "품목 줄이 길지만 이름·수량·금액이 일정한 순서로 인쇄돼 있어요." },
  luna_photo_ocr: { label: "글씨가 작거나 옅어요", description: "품목명이나 금액이 한눈에 잘 읽히지 않아요." },
} as const;

export type PurchaseOcrRoute = keyof typeof purchaseOcrOptions;
export const purchaseOcrSelectionRoutes = ["qwen_ocr", "qwen_photo_ocr", "luna_photo_ocr"] as const;
export const purchaseOcrSelectionPath = "/capture/select";

export function parsePurchaseOcrRoute(value: string | null): PurchaseOcrRoute | undefined {
  return value && Object.hasOwn(purchaseOcrOptions, value) ? value as PurchaseOcrRoute : undefined;
}

export function capturePathForDirection(direction: string, source?: "file") {
  if (direction === "purchase") {
    return source === "file" ? `${purchaseOcrSelectionPath}?source=file` : purchaseOcrSelectionPath;
  }
  const params = new URLSearchParams({ direction });
  if (source === "file") params.set("source", "file");
  return `/capture?${params.toString()}`;
}
