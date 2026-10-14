import type { ReceiptDetails, ReceiptLineItem } from "../api/receipts";

const fields = [
  ["business_number","사업자등록번호",false], ["address","사업장 주소",false], ["phone","전화번호",false],
  ["supply_amount","공급가액 (원)",true], ["vat_amount","부가세 (원)",true], ["tax_free_amount","면세금액 (원)",true],
  ["payment_method","결제수단",false], ["approval_number","승인번호",false], ["receipt_number","영수증·문서번호",false],
] as const;

export function ReceiptDetailsForm({value,original,confirmed,onChange}: {
  value:ReceiptDetails; original:ReceiptDetails; confirmed:boolean; onChange:(value:ReceiptDetails)=>void;
}) {
  function updateItem(index:number,key:keyof ReceiptLineItem,raw:string) {
    onChange({...value,items:(value.items??[]).map((item,i)=>i===index?{...item,[key]:key==="name"?raw:raw===""?null:Number(raw)}:item)});
  }
  return <section className="receipt-details-form"><h2 className="section-title">영수증 상세 정보</h2>
    <p className="muted">아래 항목은 원본에 있는 경우 입력해 주세요. 영수증에 없는 항목은 비워두어도 됩니다.</p>
    <div className="field-grid">{fields.map(([key,label,numeric])=><label className="form-field" key={key}>
      <span className="form-field__label">{label}</span><small className={original[key]!=null?"status-label--done":"muted"}>{confirmed?"확인한 정보":original[key]!=null?"추출됨":"인식값 없음 · 원본 확인"}</small>
      <input className="input" value={value[key]??""} type={numeric?"number":"text"} min={numeric?0:undefined} step={numeric?1:undefined} inputMode={numeric?"numeric":undefined}
        maxLength={key==="address"?300:key==="business_number"?30:key==="receipt_number"?60:40} onChange={e=>onChange({...value,[key]:e.target.value===""?null:numeric?Number(e.target.value):e.target.value})}/>
    </label>)}</div>
    <h3 className="section-title">품목 내역</h3><p className="footnote">자동으로 구조화하지 못한 품목은 원문과 비교해 입력해 주세요.</p>
    {(value.items??[]).map((item,index)=><fieldset className="receipt-item" key={index}><legend>품목 {index+1}</legend>
      <label className="form-field">품목명<input className="input" maxLength={200} value={item.name} onChange={e=>updateItem(index,"name",e.target.value)}/></label>
      <div className="field-grid">{([["quantity","수량"],["unit_price","단가 (원)"],["amount","금액 (원)"]] as const).map(([key,label])=><label className="form-field" key={key}>{label}<input className="input" type="number" min="0" step={key==="quantity"?"any":"1"} value={item[key]??""} onChange={e=>updateItem(index,key,e.target.value)}/></label>)}</div>
      <button className="text-link danger-text" onClick={()=>onChange({...value,items:value.items?.filter((_,i)=>i!==index)})}>품목 삭제</button>
    </fieldset>)}
    <button className="btn btn--secondary" disabled={(value.items?.length??0)>=100} onClick={()=>onChange({...value,items:[...(value.items??[]),{name:"",quantity:null,unit_price:null,amount:null}]})}>+ 품목 추가</button>
    <h3 className="section-title">그 밖의 영수증 정보</h3>
    {(value.additional_fields??[]).map((item,index)=><div className="receipt-item" key={index}><div className="field-grid"><label className="form-field">항목명<input className="input" maxLength={100} value={item.label} onChange={e=>onChange({...value,additional_fields:value.additional_fields?.map((row,i)=>i===index?{...row,label:e.target.value}:row)})}/></label><label className="form-field">내용<input className="input" maxLength={1000} value={item.value} onChange={e=>onChange({...value,additional_fields:value.additional_fields?.map((row,i)=>i===index?{...row,value:e.target.value}:row)})}/></label></div><button className="text-link danger-text" onClick={()=>onChange({...value,additional_fields:value.additional_fields?.filter((_,i)=>i!==index)})}>항목 삭제</button></div>)}
    <button className="btn btn--secondary" disabled={(value.additional_fields?.length??0)>=50} onClick={()=>onChange({...value,additional_fields:[...(value.additional_fields??[]),{label:"",value:""}]})}>+ 추가 정보 입력</button>
  </section>;
}
