// 매출 보관함 '수정'을 누른 순간의 상태. 수정 화면의 업로드·교체·삭제는 바로 서버에 반영되므로,
// '수정 완료' 없이 나가면 이 상태로 되돌린다. 상세 보기 화면에 다녀와도 남도록 세션 저장소에 둔다.
export type SourceCheck = {
  status: string; query_start?: string; query_end?: string; basis?: string; reason?: string; document_ids: number[];
};
export type SalesEditSnapshot = {
  status: string;
  sourceStatuses: Record<string, SourceCheck>;
  otherTotal: {total_amount: number; supporting_evidence?: string} | null;
  documentIds: number[];
};

const key = (period: string) => `sales-edit-snapshot:${period}`;

export function saveSalesEditSnapshot(period: string, snapshot: SalesEditSnapshot) {
  try { sessionStorage.setItem(key(period), JSON.stringify(snapshot)); } catch { /* 저장소를 못 쓰면 되돌리기만 생략한다 */ }
}

export function loadSalesEditSnapshot(period: string): SalesEditSnapshot | null {
  try { return JSON.parse(sessionStorage.getItem(key(period)) ?? "null"); } catch { return null; }
}

export function clearSalesEditSnapshot(period: string) {
  try { sessionStorage.removeItem(key(period)); } catch { /* 무시 */ }
}

/** 출처 연결 상태가 같은지(파일·상태·조회 범위·근거). */
export function sameSourceCheck(a?: SourceCheck, b?: SourceCheck) {
  const pick = (c?: SourceCheck) => [c?.status ?? "자료 없음", c?.document_ids ?? [], c?.query_start ?? null, c?.query_end ?? null, c?.basis ?? null, c?.reason ?? null];
  return JSON.stringify(pick(a)) === JSON.stringify(pick(b));
}
