import type { TransactionApi } from "../api/transactions";
import { REVIEW_LABELS, reviewStatusClass } from "../hooks/reviewState";

type Reference = { title?: string; locator?: string; url?: string; source_id?: string };

// 매입 거래의 공제 분석 결과(판단·이유·근거). 보관함과 전체 보기 화면이 같이 쓴다.
export function AnalysisResult({ transaction }: { transaction: TransactionApi }) {
  let references: Reference[] = [];
  try { const value: unknown = JSON.parse(transaction.legal_references_json ?? "[]"); if (Array.isArray(value)) references = value.filter(r => r && typeof r === "object"); } catch { /* Show missing evidence below. */ }
  return <>
    <p className={`peek-verdict status-label ${reviewStatusClass(transaction)}`}>{REVIEW_LABELS[transaction.review_status] ?? "확인 필요"}</p><p className="peek-reason">{transaction.analysis_reason ?? "아직 연결된 분석 결과가 없습니다."}</p>
    <h3>판례·세법 근거</h3>{references.length ? references.map((ref,i)=><article className="card ref-card" key={i}><strong>{ref.title || ref.source_id}</strong><p>{ref.locator}</p>{typeof ref.url==="string" && /^https?:\/\//i.test(ref.url) && <a className="text-link" href={ref.url} target="_blank" rel="noreferrer">근거 원문 열기 ↗</a>}</article>) : <p className="muted">연결된 근거 자료가 없습니다. 근거를 확인한 뒤 판단해 주세요.</p>}
  </>;
}
