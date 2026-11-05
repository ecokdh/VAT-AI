import { useState } from "react";
import type { ReceiptRecognition } from "../api/receipts";

const labels: Record<string, string> = { vendor: "상호", branch: "지점", business_number: "사업자등록번호", transaction_datetime: "거래일시", printed_total_amount: "인쇄 합계", payment_amount: "실제 결제액", supply_amount: "공급가액", taxable_supply_amount: "과세 공급가액", vat_amount: "부가세", tax_exempt_amount: "면세금액", discount_amount: "인쇄 할인 합계", subtotal_amount: "소계" };
// 기본 화면에는 핵심 항목과 앞쪽 품목만 보여 주고, 나머지는 '전체 정보 확인'에서 펼친다.
const SUMMARY_FIELDS = ["vendor", "business_number", "transaction_datetime", "payment_amount"];
const PREVIEW_ITEMS = 3;
const show = (v: unknown) => v == null ? "읽은 값 없음" : typeof v === "number" ? v.toLocaleString("ko-KR") : typeof v === "object" ? JSON.stringify(v) : String(v);

export function RecognitionDetails({result}: {result?: ReceiptRecognition | null}) {
  const [full, setFull] = useState(false);
  if (!result) return null;
  if (result.error_code) return <div className="banner banner--error" role="alert">문서 인식 실패: {result.error_code}</div>;
  const doc = result.document;
  if (!doc) return null;
  const fields = full ? Object.entries(doc.fields) : SUMMARY_FIELDS.map(k => [k, doc.fields[k]] as const);
  const checks = [...doc.conflicts.map(k => `${labels[k] ?? k}: 서로 다른 후보가 있음`), ...doc.uncertain];
  return <section className="card" style={{margin: "20px 0", padding: 16}}>
    <h2 className="section-title">{result.value_source === 'user_review' ? '확인한 거래 · 세금 · 품목' : '사진에서 읽은 거래 · 세금 · 품목'}</h2>
    {full && <p>인쇄된 값만 표시합니다. 빈 값은 인쇄 없음과 판독 실패를 구분하지 못한 상태일 수 있습니다.</p>}
    {fields.map(([k,v]) => <div className="field-row" key={k}><span className="field-row__label">{labels[k] ?? k}</span><span className="field-row__value">{show(v)}</span></div>)}
    {checks.length > 0 && <div role="status"><h3>확인할 내용</h3><ul>{checks.map((reason,i) => <li key={i}>{reason}</li>)}</ul></div>}
    <h3>품목 · {doc.items.length}행</h3>
    {full ? <div style={{overflowX: "auto"}} tabIndex={0} aria-label="품목 표 · 가로 스크롤"><table style={{width:"100%",minWidth:640,textAlign:"left"}}><thead><tr><th>이름</th><th>유형</th><th>수량</th><th>단가</th><th>행 금액</th><th>연결 상품</th></tr></thead><tbody>{doc.items.map((item,i) => <tr key={i}><td>{item.name}</td><td>{item.row_type === "item" ? "상품" : item.row_type === "option" ? "옵션" : "할인"}</td><td>{item.quantity ?? "—"}</td><td>{item.unit_price ?? "—"}</td><td>{item.line_amount ?? "—"}</td><td>{item.parent_row === null ? "—" : doc.items[item.parent_row]?.name ?? "연결 오류"}</td></tr>)}</tbody></table></div>
      : <>{doc.items.slice(0, PREVIEW_ITEMS).map((item,i) => <div className="field-row" key={i}><span className="field-row__label">{i+1}. {item.name}</span><span className="field-row__value">{item.quantity ?? "—"}개 · {item.line_amount == null ? "금액 미확인" : `${show(item.line_amount)}원`}</span></div>)}
        {doc.items.length > PREVIEW_ITEMS && <p className="muted">외 {doc.items.length - PREVIEW_ITEMS}개 품목</p>}</>}
    <button type="button" className="btn btn--secondary" style={{width: "100%", marginTop: 16}} aria-expanded={full} onClick={() => setFull(v => !v)}>{full ? "간단히 보기" : "전체 정보 확인"}</button>
  </section>;
}
