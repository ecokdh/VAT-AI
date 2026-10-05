import type { StructuredItem } from "../api/receipts";

export interface DiscountDraft {
  id: string;
  kind: "DISCOUNT" | "COUPON";
  scope: "ITEM" | "GROUP" | "TRANSACTION";
  amount: string;
  item_ids: string[];
  included_in_line_amounts: boolean | null;
  included_in_discount_id: string | null;
}

export function DiscountEditor({ discounts, items, onChange, disabled }: {
  discounts: DiscountDraft[]; items: Pick<StructuredItem, "id" | "name">[];
  onChange: (values: DiscountDraft[]) => void; disabled: boolean;
}) {
  function edit(id: string, patch: Partial<DiscountDraft>) {
    onChange(discounts.map(value => value.id === id ? { ...value, ...patch } : value));
  }
  return <section aria-label="할인과 쿠폰" style={{ marginBottom: 24 }}>
    <h2 style={{ fontSize: 18 }}>할인과 쿠폰</h2>
    <p className="muted">이미 행 금액에 포함된 할인은 다시 차감하지 않습니다. 공동 할인은 품목에 임의 배분하지 않습니다.</p>
    {discounts.map((discount, index) => <fieldset key={discount.id} style={{ padding: 12, marginBottom: 12 }}>
      <legend>할인 {index + 1}</legend>
      <label htmlFor={`discount-kind-${discount.id}`}>종류</label>
      <select id={`discount-kind-${discount.id}`} className="input" value={discount.kind} disabled={disabled}
        onChange={e => edit(discount.id, { kind: e.target.value as DiscountDraft["kind"] })}>
        <option value="DISCOUNT">할인</option><option value="COUPON">쿠폰</option>
      </select>
      <label htmlFor={`discount-amount-${discount.id}`}>금액</label>
      <input id={`discount-amount-${discount.id}`} className="input" value={discount.amount} inputMode="decimal" disabled={disabled}
        onChange={e => edit(discount.id, { amount: e.target.value })} />
      <label htmlFor={`discount-scope-${discount.id}`}>적용 범위</label>
      <select id={`discount-scope-${discount.id}`} className="input" value={discount.scope} disabled={disabled}
        onChange={e => edit(discount.id, { scope: e.target.value as DiscountDraft["scope"], item_ids: [] })}>
        <option value="TRANSACTION">거래 전체</option><option value="ITEM">품목 하나</option><option value="GROUP">품목 그룹</option>
      </select>
      {discount.scope !== "TRANSACTION" && <div>
        <p>대상 품목 · 새 품목은 먼저 저장한 뒤 선택하세요.</p>
        {items.filter(item => item.id).map(item => <label key={item.id} style={{ display: "block" }}>
          <input type="checkbox" disabled={disabled} checked={discount.item_ids.includes(item.id!)}
            onChange={e => edit(discount.id, { item_ids: e.target.checked
              ? discount.scope === "ITEM" ? [item.id!] : [...discount.item_ids, item.id!]
              : discount.item_ids.filter(id => id !== item.id) })} /> {item.name}
        </label>)}
      </div>}
      <label htmlFor={`discount-in-lines-${discount.id}`}>행 금액에 이미 반영됐나요?</label>
      <select id={`discount-in-lines-${discount.id}`} className="input" disabled={disabled}
        value={discount.included_in_line_amounts === null ? "unknown" : String(discount.included_in_line_amounts)}
        onChange={e => edit(discount.id, { included_in_line_amounts: e.target.value === "unknown" ? null : e.target.value === "true" })}>
        <option value="unknown">미확인</option><option value="true">이미 반영됨</option><option value="false">아직 반영되지 않음</option>
      </select>
      <label htmlFor={`discount-in-other-${discount.id}`}>다른 할인 금액에 포함됐나요?</label>
      <select id={`discount-in-other-${discount.id}`} className="input" disabled={disabled} value={discount.included_in_discount_id ?? ""}
        onChange={e => edit(discount.id, { included_in_discount_id: e.target.value || null })}>
        <option value="">별도 할인·미확인</option>{discounts.filter(d => d.id !== discount.id).map(d => <option key={d.id} value={d.id}>
          할인 {discounts.findIndex(value => value.id === d.id) + 1} · {d.kind === "COUPON" ? "쿠폰" : "할인"} · {d.amount}원
        </option>)}
      </select>
      <button className="btn btn--secondary" disabled={disabled} onClick={() => onChange(discounts.filter(d => d.id !== discount.id)
        .map(d => d.included_in_discount_id === discount.id ? { ...d, included_in_discount_id: null } : d))}>할인 삭제</button>
    </fieldset>)}
    <button className="btn btn--secondary" disabled={disabled} onClick={() => onChange([...discounts, {
      id: crypto.randomUUID(), kind: "DISCOUNT", scope: "TRANSACTION", amount: "", item_ids: [],
      included_in_line_amounts: null, included_in_discount_id: null,
    }])}>할인·쿠폰 추가</button>
  </section>;
}
