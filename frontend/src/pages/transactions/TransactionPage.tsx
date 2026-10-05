import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { isAxiosError } from "axios";
import { PageHeader } from "../../components/PageHeader";
import { getTransaction, listTransactions, listDuplicateIssues, updateItemUsage, linkOriginal,
  resolveDuplicate, linkEvidence, type TransactionApi, type DuplicateIssue } from "../../api/transactions";
import type { StructuredItem } from "../../api/receipts";

function label(t: TransactionApi) {
  return `${t.facts.vendor ?? "거래처 미확인"} · ${t.facts.date ?? "날짜 미확인"} · ${t.facts.total_amount?.toLocaleString() ?? "금액 미확인"}원 · 증빙 ${t.receipts.map(r => r.id).join(", ")}`;
}

export function TransactionPage() {
  const { id } = useParams();
  const [transaction, setTransaction] = useState<TransactionApi | null>(null);
  const [transactions, setTransactions] = useState<TransactionApi[]>([]);
  const [issues, setIssues] = useState<DuplicateIssue[]>([]);
  const [selection, setSelection] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function reload() {
    if (!id) return;
    const [current, all, candidates] = await Promise.all([getTransaction(id), listTransactions(), listDuplicateIssues()]);
    setTransaction(current); setTransactions(all); setIssues(candidates); setSelection("");
  }
  useEffect(() => {
    let active = true;
    if (!id) return;
    Promise.all([getTransaction(id), listTransactions(), listDuplicateIssues()]).then(([current, all, candidates]) => {
      if (active) { setTransaction(current); setTransactions(all); setIssues(candidates); }
    }).catch(() => { if (active) setError("거래를 불러오지 못했습니다."); });
    return () => { active = false; };
  }, [id]);

  async function save(action: () => Promise<unknown>) {
    if (busy) return;
    setBusy(true); setError(""); setNotice("");
    try { await action(); await reload(); setNotice("저장한 상태를 다시 불러왔습니다."); }
    catch (e) {
      const message = isAxiosError(e) ? e.response?.data?.error?.message : null;
      setError(message ?? "저장하지 못했습니다. 최신 상태를 확인하세요.");
      if (isAxiosError(e) && e.response?.status === 409) {
        try { await reload(); } catch { setError("최신 상태를 불러오지 못했습니다. 다시 불러오세요."); }
      }
    } finally { setBusy(false); }
  }
  const attachAdjustment = Boolean(transaction?.adjustment_type && transaction.original_transaction_id);
  const choices = transactions.filter(t => t.id !== id && t.workflow_status !== "MERGED" && (attachAdjustment
    ? t.adjustment_type === transaction?.adjustment_type && t.receipts.length > 0
      && (!t.original_transaction_id || t.original_transaction_id === transaction?.original_transaction_id)
    : !t.adjustment_type));
  const selected = choices.find(t => t.id === selection);
  const candidates = issues.filter(i => i.active !== false && !i.resolved && i.receipts.some(r => r.transaction_id === id));
  const adjustments = transactions.filter(t => t.original_transaction_id === id && t.workflow_status !== "MERGED");

  return <div className="page">
    <PageHeader title="확정 거래" />
    {error && <p role="alert" className="banner banner--error">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {!transaction ? <p>거래를 불러오는 중입니다.</p> : <div className="card">
      <h2>{label(transaction)}</h2>
      <p>증빙 검사: {transaction.evidence_validation.validation_status}
        {transaction.evidence_validation.conflicts.length > 0 && ` · 충돌: ${transaction.evidence_validation.conflicts.join(", ")}`}</p>
      <p className="muted">{transaction.facts.ocr_confirmed ? "OCR 사실을 확인한 거래입니다." : "증빙의 OCR 확인이 필요한 조정거래입니다."} 세무분석 및 공제 가능성은 확정되지 않았습니다.</p>
      {transaction.workflow_status === "MERGED" && <p>다른 거래에 증빙을 병합한 기록입니다.</p>}
      <h3>연결된 증빙</h3>
      {transaction.receipts.map(r => <p key={r.id}><Link to={`/receipts/${r.id}/edit`}>증빙 {r.id} · 사진과 판독값 확인</Link></p>)}
      <h3>대표 증빙의 품목 용도</h3>
      <p className="muted">다른 증빙의 품목을 추가 구매로 합산하지 않습니다.</p>
      {transaction.canonical_line_items.map(item => <div className="form-field" key={item.id}>
        <label htmlFor={`usage-${item.id}`}>{item.name} · {item.line_amount?.toLocaleString() ?? "금액 미확인"}원</label>
        <select id={`usage-${item.id}`} className="input" value={item.usage} disabled={busy || !item.id || transaction.workflow_status === "MERGED"}
          onChange={e => void save(() => updateItemUsage(transaction.id, item.id!, transaction.revision, e.target.value as StructuredItem["usage"]))}>
          <option value="UNKNOWN">미확인</option><option value="BUSINESS">사업용</option>
          <option value="PERSONAL">개인용</option><option value="MIXED">혼합</option>
        </select>
      </div>)}
      {transaction.original_transaction_id && <p>원거래: <Link to={`/transactions/${transaction.original_transaction_id}`}>연결된 원거래 확인</Link></p>}
      {adjustments.length > 0 && <section aria-label="연결된 조정거래">
        <h3>연결된 반품·취소·조정</h3>
        {adjustments.map(t => <p key={t.id}><Link to={`/transactions/${t.id}`}>{t.adjustment_type === "RETURN" ? "반품" : t.adjustment_type === "CANCELLATION" ? "취소" : "금액 조정"} · {t.facts.total_amount?.toLocaleString() ?? "금액 미확인"}원</Link></p>)}
      </section>}
      {transaction.workflow_status !== "MERGED" && (!transaction.adjustment_type || transaction.workflow_status === "UNRESOLVED_ADJUSTMENT" || attachAdjustment) && <>
        <h3>{attachAdjustment ? "반품·취소 증빙 연결" : transaction.adjustment_type ? "반품·취소의 원거래 연결" : "같은 거래의 다른 증빙 연결"}</h3>
        <label htmlFor="transaction-choice">{transaction.adjustment_type && !attachAdjustment ? "원거래 선택" : "추가 증빙이 있는 거래 선택"}</label>
        <select id="transaction-choice" className="input" value={selection} disabled={busy} onChange={e => setSelection(e.target.value)}>
          <option value="">선택하세요</option>{choices.map(t => <option key={t.id} value={t.id}>{label(t)}</option>)}
        </select>
        <p className="muted">{attachAdjustment ? "같은 종류·금액·거래처의 반품 증빙을 연결합니다. 반품 금액은 한 번만 집계합니다." : transaction.adjustment_type ? "원거래의 남은 금액을 넘는 반품·취소는 연결할 수 없습니다." : "선택한 거래의 모든 증빙을 현재 거래에 연결합니다. 거래처와 총액이 같아야 합니다."}</p>
        <button className="btn btn--secondary" disabled={busy || !selected || ((!transaction.adjustment_type || attachAdjustment) && !selected.receipts.length)}
          onClick={() => selected && void save(() => transaction.adjustment_type && !attachAdjustment ? linkOriginal(transaction.id, transaction.revision, selected)
            : linkEvidence(transaction, selected, selected.receipts[0], transactions.find(t => t.id === transaction.original_transaction_id)?.revision, transactions))}>선택한 거래와 연결</button>
      </>}
      {candidates.length > 0 && <h3>중복 후보 검토</h3>}
      {candidates.map(issue => <div key={issue.id} className="form-field">
        <p>증빙 {issue.receipts.map(r => r.id).join(" / ")} · {({ SAME_FILE: "동일 파일", SIMILAR_IMAGE: "비슷한 사진", SAME_APPROVAL_SIGNATURE: "같은 승인 정보" } as Record<string, string>)[issue.reason] ?? issue.reason}</p>
        <p className="muted">비슷한 사진은 서로 다른 영수증일 수 있습니다. 사진을 대조하고 선택하세요.</p>
        {issue.receipts.map(r => <p key={r.id}><Link to={`/receipts/${r.id}/edit`}>증빙 {r.id} 사진 보기</Link></p>)}
        <button className="btn btn--secondary" disabled={busy} onClick={() => void save(() => resolveDuplicate(issue, null, []))}>별도 거래로 유지</button>
        <button className="btn btn--secondary" disabled={busy || transaction.workflow_status === "MERGED" || Boolean(transaction.adjustment_type)
          || issue.receipts.some(r => !r.transaction_id || !transactions.some(t => t.id === r.transaction_id))
          || issue.receipts.some(r => transactions.some(t => t.id === r.transaction_id && (t.adjustment_type || t.workflow_status === "MERGED")))
          || new Set(issue.receipts.map(r => r.transaction_id)).size !== 2}
          onClick={() => void save(() => resolveDuplicate(issue, transaction, transactions))}>현재 거래로 증빙 병합</button>
      </div>)}
      <button className="btn btn--secondary" disabled={busy} onClick={() => void save(reload)}>최신 상태 다시 불러오기</button>
    </div>}
  </div>;
}
