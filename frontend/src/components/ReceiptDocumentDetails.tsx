import {useEffect,useState} from 'react';
import {getReceipt,type ReceiptProcessingApi} from '../api/receipts';
import {useMaskedFormat} from '../hooks/useMaskedFormat';

const labels:Record<string,string>={vendor:'공급자 상호',branch:'지점',business_number:'사업자등록번호',transaction_datetime:'거래일시',printed_total_amount:'인쇄 합계',subtotal_amount:'소계',payment_amount:'실제 결제액',supply_amount:'공급가액',taxable_supply_amount:'과세 공급가액',vat_amount:'부가가치세',tax_exempt_amount:'면세금액',discount_amount:'할인액'};
const extras:Record<string,string>={address:'주소',phone:'전화번호',payment_method:'결제수단',approval_number:'승인번호',receipt_number:'영수증 번호'};

/** Load only after a transaction's details are opened. Keep full saved document. */
export function ReceiptDocumentDetails({receiptId}:{receiptId:number}){
 const [receipt,setReceipt]=useState<ReceiptProcessingApi|null>(null),[error,setError]=useState(false);
 const fmt=useMaskedFormat();
 useEffect(()=>{let active=true;setReceipt(null);setError(false);getReceipt(receiptId).then(r=>{if(active)setReceipt(r);}).catch(()=>{if(active)setError(true);});return()=>{active=false;};},[receiptId]);
 if(error)return <p role="alert">전체 증빙 정보를 불러오지 못했습니다. 다시 펼쳐 확인해 주세요.</p>;
 if(!receipt)return <p role="status">전체 증빙 정보를 불러오는 중입니다.</p>;
 const doc=receipt.review?.document??receipt.recognition?.document;
 const fields:Record<string,string|number|null|undefined>=doc?.fields??{vendor:receipt.vendor,business_number:receipt.details.business_number,transaction_datetime:receipt.date,payment_amount:receipt.amount,supply_amount:receipt.details.supply_amount,vat_amount:receipt.details.vat_amount,tax_exempt_amount:receipt.details.tax_free_amount};
 const items=doc?.items??(receipt.details.items??[]).map(i=>({...i,line_amount:i.amount,row_type:'item',parent_row:null}));
 const row=(label:string,value:unknown,money=false)=><div className="field-row" key={label}><span>{label}</span><span style={{textAlign:'right',overflowWrap:'anywhere',maxWidth:'65%'}}>{value==null||value===''?'미확인':money&&typeof value==='number'?fmt.won(value):String(value)}</span></div>;
 return <section aria-label="전체 증빙 정보">
  <h3>전체 증빙 정보</h3>
  {Object.entries(labels).map(([key,label])=>row(label,fields[key],key.endsWith('_amount')))}
  {Object.entries(extras).map(([key,label])=>row(label,receipt.details[key as keyof typeof receipt.details]))}
  {(receipt.details.additional_fields??[]).map((f,i)=><div className="field-row" key={`extra-${i}`}><span>{f.label}</span><span>{f.value}</span></div>)}
  <h3>전체 품목 · {items.length}행</h3>
  {!items.length&&<p className="muted">저장된 품목 정보가 없습니다.</p>}
  {items.map((item,i)=><article key={i} style={{padding:'12px 0',borderBottom:'1px solid #e5edf9',overflowWrap:'anywhere'}}><strong>{i+1}. {item.name}</strong>
   {row('행 유형',item.row_type==='discount'?'할인':item.row_type==='option'?'옵션':'상품')}
   {row('수량',item.quantity)}{row('단가',item.unit_price,true)}{row('행 금액',item.line_amount,true)}
   {item.parent_row!=null&&row('연결 상품',items[item.parent_row]?.name??'연결 확인 필요')}
  </article>)}
  <p className="muted">미확인은 인쇄 없음으로 확정한 표시가 아닙니다.</p>
 </section>;
}
