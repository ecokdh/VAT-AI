import { useEffect, useState } from "react";
import { editTransactionReceipt, setFixedAsset, type TransactionApi } from "../api/transactions";
import { matchesReviewStatus, reviewLabel, reviewStatusClass } from "../hooks/reviewState";
import { formatWon } from "../utils/format";
import { AnalysisResult } from "./AnalysisResult";
import { ReceiptDocumentDetails } from "./ReceiptDocumentDetails";
import { ReceiptPreview } from "./ReceiptPreview";
import { SlidePanel } from "./SlidePanel";
import { TransactionQuestions } from "./TransactionQuestions";

// 거래 상세 시트. 보관함과 전체 보기가 같은 내용(상태·고정자산·증빙 정보 수정·거래 용도·삭제)을 보여 준다.
export function TransactionDetailSheet({ transaction, resultMode, onClose, onUpdated, onSaved, onDelete }: {
  transaction: TransactionApi | null; resultMode: boolean; onClose: () => void;
  onUpdated: (updated: TransactionApi) => void; onSaved: () => void; onDelete: (transaction: TransactionApi) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [fixedAssetBusy, setFixedAssetBusy] = useState(false);
  const [fixedAssetError, setFixedAssetError] = useState("");
  useEffect(() => { setEditing(false); setFixedAssetError(""); }, [transaction?.id, resultMode]);

  async function toggleFixedAsset(item: TransactionApi, value: boolean) {
    setFixedAssetBusy(true); setFixedAssetError("");
    try { onUpdated(await setFixedAsset(item.id, value)); }
    catch { setFixedAssetError("고정자산 여부를 저장하지 못했습니다. 다시 시도해 주세요."); }
    finally { setFixedAssetBusy(false); }
  }

  const t = transaction;
  const waiting = !!t && t.direction === "purchase" && matchesReviewStatus(t, "waiting");
  return <SlidePanel open={!!t} label={resultMode ? "분석 결과" : "거래 상세"} title={t ? t.description || t.vendor : ""} onClose={onClose}>{t && (resultMode ? <AnalysisResult transaction={t} /> : <>
    <p>{t.transaction_date} · {t.vendor}</p>
    <div className="peek-amount-row"><strong className="peek-amount">{formatWon(t.total_amount)}</strong>{t.receipt_id && <button type="button" className="text-link" onClick={() => setEditing(v => !v)}>{editing ? "수정 취소" : "수정하기"}</button>}</div>
    <p className={`status-label ${waiting ? "status-label--wait" : reviewStatusClass(t)}`}>{reviewLabel(t).replace(/^[✓◷]\s*/, "")}</p>
    {/* 수정 중에는 아래 전체 증빙 정보의 입력칸(상호·공급가액·부가세)으로 고친다 */}
    {!editing && <><div className="field-row"><span>거래처</span><strong>{t.vendor}</strong></div><div className="field-row"><span>공급가액</span><span>{t.supply_amount == null ? "확인 필요" : formatWon(t.supply_amount)}</span></div><div className="field-row"><span>부가세</span><span>{t.vat_amount == null ? "확인 필요" : formatWon(t.vat_amount)}</span></div></>}
    {t.direction === "purchase" && <><label className="check-row"><input type="checkbox" checked={t.is_fixed_asset} disabled={fixedAssetBusy} onChange={e => void toggleFixedAsset(t, e.target.checked)} />고정자산 (1년 이상 쓰는 장비·시설)</label>
      <p className="footnote fixed-asset-note">{fixedAssetError || "세금계산서로 받으면 신고서 (12) 고정자산매입에 들어갑니다. 체크해도 공제 분석은 다시 하지 않아요."}</p></>}
    {t.receipt_id && <><ReceiptPreview id={t.receipt_id} controls /><ReceiptDocumentDetails receiptId={t.receipt_id} edit={editing ? { save: (doc, details) => editTransactionReceipt(t.id, doc, details).then(onUpdated), onCancel: () => setEditing(false), onSaved: () => { setEditing(false); onSaved(); } } : undefined} />
      {!editing && <button type="button" className="btn sheet-edit-button" onClick={() => setEditing(true)}>정보 수정하기</button>}</>}
    {!editing && <>{t.direction === "purchase" && <TransactionQuestions id={t.id} onSaved={onSaved} />}
      <button type="button" className="text-link danger" onClick={() => onDelete(t)}>거래 삭제</button></>}
  </>)}</SlidePanel>;
}
