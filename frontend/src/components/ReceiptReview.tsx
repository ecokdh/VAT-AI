import { useEffect, useRef, useState } from "react";
import { getReceiptImage, type StructuredItem } from "../api/receipts";

export type ItemDraft = Omit<StructuredItem, "quantity" | "printed_unit_price" | "line_amount" | "discount_amount"> & {
  key: string;
  quantity: string;
  printed_unit_price: string;
  line_amount: string;
  discount_amount: string;
};

function itemDraft(item: StructuredItem): ItemDraft {
  return { ...item, key: item.id ?? crypto.randomUUID(), quantity: String(item.quantity ?? ""),
    printed_unit_price: String(item.printed_unit_price ?? ""), line_amount: String(item.line_amount ?? ""),
    discount_amount: String(item.discount_amount ?? "") };
}

export function ReceiptReview({ receiptId, rows, onChange, disabled }: {
  receiptId: number; rows: ItemDraft[]; onChange: (rows: ItemDraft[]) => void; disabled: boolean;
}) {
  const [photo, setPhoto] = useState("");
  const [photoError, setPhotoError] = useState("");
  const [dimensions, setDimensions] = useState({ width: 1, height: 1 });
  const [selected, setSelected] = useState<string | null>(null);
  const photoViewport = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let active = true;
    let url = "";
    getReceiptImage(receiptId).then(blob => {
      if (!active) return;
      url = URL.createObjectURL(blob);
      setPhoto(url);
      setPhotoError("");
    }).catch(() => { if (active) setPhotoError("원본 사진을 불러오지 못했습니다."); });
    return () => { active = false; if (url) URL.revokeObjectURL(url); };
  }, [receiptId]);
  const selectedRow = rows.find(row => row.key === selected);
  const boxes = Object.values(selectedRow?.sources ?? {}).flatMap(source => source.boxes ?? []);
  useEffect(() => {
    const viewport = photoViewport.current;
    const selectedItem = rows.find(row => row.key === selected);
    const regions = Object.values(selectedItem?.sources ?? {}).flatMap(source => source.boxes ?? []);
    if (viewport && regions.length) {
      viewport.scrollTop = Math.max(0, Math.min(...regions.map(box => box.y)) * viewport.clientWidth / dimensions.width - viewport.clientHeight / 3);
    }
  }, [selected, rows, dimensions.width]);
  function edit(index: number, patch: Partial<ItemDraft>) {
    onChange(rows.map((row, i) => i === index ? { ...row, ...patch } : row));
  }
  function move(index: number, offset: number) {
    const next = [...rows];
    [next[index], next[index + offset]] = [next[index + offset], next[index]];
    onChange(next);
  }
  return <section aria-label="사진과 품목 대조" style={{ marginBottom: 24 }}>
    <h2 style={{ fontSize: 18 }}>원본 사진과 품목</h2>
    {photoError && <p role="status">{photoError}</p>}
    {photo && <div ref={photoViewport} style={{ maxHeight: 480, overflow: "auto", border: "1px solid #d1d5db", borderRadius: 12, marginBottom: 16 }}>
      <div style={{ position: "relative" }}>
        <img src={photo} alt="업로드한 영수증 원본" style={{ display: "block", width: "100%" }}
          onLoad={e => setDimensions({ width: e.currentTarget.naturalWidth, height: e.currentTarget.naturalHeight })} />
        <svg aria-label="선택한 품목의 인식 영역" viewBox={`0 0 ${dimensions.width} ${dimensions.height}`}
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}>
          {boxes.map((box, index) => <rect key={index} {...box} fill="rgba(37,99,235,.15)" stroke="#2563eb" strokeWidth={Math.max(2, dimensions.width / 300)} />)}
        </svg>
      </div>
    </div>}
    <p className="muted">품목을 선택하면 사진의 인식 영역이 표시됩니다. 인쇄 단가와 행 금액 ÷ 수량으로 구한 실효 단가는 별도로 확인하세요.</p>
    {rows.map((row, index) => <fieldset key={row.key} onFocus={() => setSelected(row.key)}
      style={{ padding: 12, marginBottom: 12, borderRadius: 12, border: `2px solid ${selected === row.key ? "#2563eb" : "#e5e7eb"}` }}>
      <legend>품목 {index + 1}</legend>
      <button type="button" className="btn btn--secondary" onClick={() => setSelected(row.key)}>사진에서 위치 확인</button>
      {([ ["name", "품목명"], ["specification", "규격"], ["unit", "단위"], ["quantity", "수량"],
        ["printed_unit_price", "인쇄 단가"], ["line_amount", "행 금액"], ["discount_amount", "품목 할인"] ] as const).map(([key, label]) => {
        const source = row.sources[key];
        return <div className="form-field" key={key}>
          <label className="form-field__label" htmlFor={`${row.key}-${key}`}>{label}</label>
          <input id={`${row.key}-${key}`} className="input" disabled={disabled} value={row[key] ?? ""}
            onChange={e => edit(index, { [key]: e.target.value,
              sources: { ...row.sources, [key]: { ...source, kind: "manual", state: e.target.value.trim() ? "READ" : "UNREVIEWED" } } })} />
          {!row[key] && key !== "name" && <>
            <label htmlFor={`${row.key}-${key}-state`} className="muted">빈 값의 상태</label>
            <select id={`${row.key}-${key}-state`} className="input" disabled={disabled} value={source?.state === "READ" ? "UNREVIEWED" : source?.state ?? "UNREVIEWED"}
              onChange={e => edit(index, { sources: { ...row.sources, [key]: { ...source, kind: "manual", state: e.target.value as StructuredItem["sources"][string]["state"] } } })}>
              <option value="UNREVIEWED">미확인</option><option value="ABSENT">실제 미기재</option>
              <option value="FAILED">판독 실패</option><option value="NOT_APPLICABLE">해당 없음</option>
            </select>
          </>}
          {source && <small className="muted">{source.kind === "ocr" ? "OCR" : source.kind === "manual" ? "사용자 수정" : "계산"}
            {source.confidence != null ? ` · 인식 신뢰도 ${Math.round(source.confidence * 100)}%` : ""}</small>}
        </div>;
      })}
      <p className="muted">저장된 실효 단가: {row.effective_unit_price ?? "미확인"}</p>
      <div className="form-field">
        <label className="form-field__label" htmlFor={`${row.key}-tax`}>과세 표시</label>
        <select id={`${row.key}-tax`} className="input" disabled={disabled} value={row.tax_type} onChange={e => edit(index, { tax_type: e.target.value as StructuredItem["tax_type"] })}>
          <option value="UNKNOWN">미확인</option><option value="TAXABLE">과세</option><option value="EXEMPT">면세</option><option value="ZERO_RATED">영세율</option>
        </select>
      </div>
      <div className="form-field">
        <label className="form-field__label" htmlFor={`${row.key}-usage`}>사용 용도</label>
        <select id={`${row.key}-usage`} className="input" disabled={disabled} value={row.usage} onChange={e => edit(index, { usage: e.target.value as StructuredItem["usage"] })}>
          <option value="UNKNOWN">미확인</option><option value="BUSINESS">사업용</option><option value="PERSONAL">개인용</option><option value="MIXED">혼합</option>
        </select>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <button className="btn btn--secondary" disabled={disabled || index === 0} onClick={() => move(index, -1)}>위로</button>
        <button className="btn btn--secondary" disabled={disabled || index === rows.length - 1} onClick={() => move(index, 1)}>아래로</button>
        <button className="btn btn--secondary" disabled={disabled} onClick={() => onChange(rows.filter(item => item.key !== row.key))}>삭제</button>
      </div>
    </fieldset>)}
    <button className="btn btn--secondary" disabled={disabled} onClick={() => onChange([...rows, itemDraft({ id: null, name: "", quantity: null, printed_unit_price: null, line_amount: null, tax_type: "UNKNOWN", usage: "UNKNOWN", sources: {} })])}>품목 추가</button>
  </section>;
}
