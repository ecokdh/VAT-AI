import {useEffect,useState,type FormEvent,type ReactNode} from 'react';
import {isAxiosError} from 'axios';
import {getReceipt,type ReceiptDetails,type ReceiptProcessingApi,type ReceiptReview} from '../api/receipts';
import { formatWon } from "../utils/format";
import { NumberInput } from './NumberInput';

const labels:Record<string,string>={vendor:'공급자 상호',branch:'지점',business_number:'사업자등록번호',transaction_datetime:'거래일시',printed_total_amount:'인쇄 합계',subtotal_amount:'소계',payment_amount:'실제 결제액',supply_amount:'공급가액',taxable_supply_amount:'과세 공급가액',vat_amount:'부가가치세',tax_exempt_amount:'면세금액',discount_amount:'할인액'};
const extras:Record<string,string>={address:'주소',phone:'전화번호',payment_method:'결제수단',approval_number:'승인번호',receipt_number:'영수증 번호'};
const ITEM_KEYS=['name','raw_name','source_row','quantity','unit_price','line_amount','row_type','parent_row'] as const;
const itemNumbers:[string,string][]=[['quantity','수량'],['unit_price','단가'],['line_amount','행 금액']];
type Doc=ReceiptReview['document'];
type Draft={fields:Record<string,string>;extras:Record<string,string>;items:Record<string,string>[];additional:{label:string;value:string}[]};
const text=(v:unknown)=>v==null?'':String(v);
const num=(v:string)=>v.trim()===''?null:Number(v);

/** Load only after a transaction's details are opened. Keep full saved document. With `edit`, every value becomes an input and is saved together. */
export type DetailEdit={save:(document:Doc,details:ReceiptDetails,receipt:ReceiptProcessingApi)=>Promise<unknown>;onSaved:()=>void;onCancel:()=>void};

export function ReceiptDocumentDetails({receiptId,edit}:{receiptId:number;edit?:DetailEdit}){
 const [receipt,setReceipt]=useState<ReceiptProcessingApi|null>(null),[error,setError]=useState(false);
 const [draft,setDraft]=useState<Draft|null>(null),[saving,setSaving]=useState(false),[saveError,setSaveError]=useState('');
useEffect(()=>{let active=true;setReceipt(null);setError(false);getReceipt(receiptId).then(r=>{if(active)setReceipt(r);}).catch(()=>{if(active)setError(true);});return()=>{active=false;};},[receiptId]);
 if(error)return <p role="alert">전체 증빙 정보를 불러오지 못했습니다. 다시 펼쳐 확인해 주세요.</p>;
 if(!receipt)return <p role="status">전체 증빙 정보를 불러오는 중입니다.</p>;
 const doc=receipt.review?.document??receipt.recognition?.document;
 const fields:Record<string,string|number|null|undefined>=doc?.fields??{vendor:receipt.vendor,business_number:receipt.details.business_number,transaction_datetime:receipt.date,payment_amount:receipt.amount,supply_amount:receipt.details.supply_amount,vat_amount:receipt.details.vat_amount,tax_exempt_amount:receipt.details.tax_free_amount};
 const items=doc?.items??(receipt.details.items??[]).map(i=>({...i,line_amount:i.amount,row_type:'item',parent_row:null}));
 const editing=!!edit;
 const d:Draft=draft??{fields:Object.fromEntries(Object.keys(labels).map(k=>[k,text(fields[k])])),extras:Object.fromEntries(Object.keys(extras).map(k=>[k,text(receipt.details[k as keyof typeof receipt.details])])),items:items.map(i=>({name:i.name,quantity:text(i.quantity),unit_price:text(i.unit_price),line_amount:text(i.line_amount),row_type:i.row_type})),additional:receipt.details.additional_fields??[]};
 const change=(fn:(v:Draft)=>Draft)=>setDraft(fn(d));
 const input=(value:string,onChange:(v:string)=>void,label:string,numeric=false)=>numeric?<NumberInput className="input detail-input" aria-label={label} value={value} placeholder="미확인" allowDecimal allowNegative onValueChange={onChange}/>:<input className="input detail-input" aria-label={label} value={value} placeholder="미확인" onChange={e=>onChange(e.target.value)}/>;
 const show=(value:unknown,money=false)=>value==null||value===''?'미확인':money&&typeof value==='number'?formatWon(value):String(value);
 const row=(label:string,value:unknown,money=false,editor?:ReactNode)=><div className="field-row" key={label}><span>{label}</span>{editing&&editor?editor:<span style={{textAlign:'right',overflowWrap:'anywhere',maxWidth:'65%'}}>{show(value,money)}</span>}</div>;

 async function save(e:FormEvent){
  e.preventDefault();if(!edit||saving||!receipt)return;
  const outFields:Doc['fields']={...(doc?.fields??{})};
  for(const k of Object.keys(labels))outFields[k]=k.endsWith('_amount')?num(d.fields[k]):(d.fields[k].trim()||null);
  const keep=Object.fromEntries(Object.keys(labels).map(k=>[k,outFields[k]]));
  const outItems=items.map((item,i)=>({...Object.fromEntries(ITEM_KEYS.map(k=>[k,(item as Record<string,unknown>)[k]??null])),name:d.items[i].name.trim()||item.name,quantity:num(d.items[i].quantity),unit_price:num(d.items[i].unit_price),line_amount:num(d.items[i].line_amount),row_type:d.items[i].row_type,parent_row:d.items[i].row_type==='item'?null:item.parent_row??null})) as Doc['items'];
  setSaving(true);setSaveError('');
  try{await edit.save({fields:keep,items:outItems},{...Object.fromEntries(Object.entries(d.extras).map(([k,v])=>[k,v.trim()||null])),additional_fields:d.additional.filter(a=>a.label.trim())},receipt);setReceipt(await getReceipt(receiptId));setDraft(null);edit.onSaved();}
  catch(cause){setSaveError((isAxiosError(cause)&&cause.response?.data?.error?.message)||'수정 내용을 저장하지 못했습니다. 입력값은 유지됩니다.');}
  finally{setSaving(false);}
 }

 const body=<>
  <h3>전체 증빙 정보</h3>
  {Object.entries(labels).map(([key,label])=>row(label,fields[key],key.endsWith('_amount'),input(d.fields[key],v=>change(x=>({...x,fields:{...x.fields,[key]:v}})),label,key.endsWith('_amount'))))}
  {Object.entries(extras).map(([key,label])=>row(label,receipt.details[key as keyof typeof receipt.details],false,input(d.extras[key],v=>change(x=>({...x,extras:{...x.extras,[key]:v}})),label)))}
  {(editing?d.additional:receipt.details.additional_fields??[]).map((f,i)=><div className="field-row" key={`extra-${i}`}>{editing?<>{input(f.label,v=>change(x=>({...x,additional:x.additional.map((a,j)=>j===i?{...a,label:v}:a)})),'추가 항목명')}{input(f.value,v=>change(x=>({...x,additional:x.additional.map((a,j)=>j===i?{...a,value:v}:a)})),'추가 항목 내용')}</>:<><span>{f.label}</span><span>{f.value}</span></>}</div>)}
  <h3>전체 품목 · {items.length}행</h3>
  {!items.length&&<p className="muted">저장된 품목 정보가 없습니다.</p>}
  {items.map((item,i)=><article key={i} style={{padding:'12px 0',borderBottom:'1px solid #e5edf9',overflowWrap:'anywhere'}}>{editing?input(d.items[i].name,v=>change(x=>({...x,items:x.items.map((r,j)=>j===i?{...r,name:v}:r)})),`${i+1}번 품목명`):<strong>{i+1}. {item.name}</strong>}
   {row('행 유형',item.row_type==='discount'?'할인':item.row_type==='option'?'옵션':'상품',false,<select className="input detail-input" aria-label="행 유형" value={d.items[i].row_type} onChange={e=>change(x=>({...x,items:x.items.map((r,j)=>j===i?{...r,row_type:e.target.value}:r)}))}><option value="item">상품</option><option value="option">옵션</option><option value="discount">할인</option></select>)}
   {itemNumbers.map(([key,label])=>row(label,item[key as 'quantity'],key!=='quantity',input(d.items[i][key],v=>change(x=>({...x,items:x.items.map((r,j)=>j===i?{...r,[key]:v}:r)})),label,true)))}
   {item.parent_row!=null&&row('연결 상품',items[item.parent_row]?.name??'연결 확인 필요')}
  </article>)}
  {!editing&&<p className="muted">미확인은 인쇄 없음으로 확정한 표시가 아닙니다.</p>}
 </>;
 if(!editing)return <section aria-label="전체 증빙 정보">{body}</section>;
 return <form className="receipt-detail-edit" aria-label="전체 증빙 정보 수정" onSubmit={e=>void save(e)}><fieldset disabled={saving}>{body}
  {saveError&&<p className="banner banner--error" role="alert">{saveError}</p>}
  <div className="btn-row detail-edit-actions"><button type="button" className="btn btn--secondary" onClick={()=>{setDraft(null);edit.onCancel();}}>취소</button><button type="submit" className="btn btn--primary">{saving?'저장 중…':'저장'}</button></div>
 </fieldset></form>;
}
