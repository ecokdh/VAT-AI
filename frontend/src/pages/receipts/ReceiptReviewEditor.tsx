import { useEffect, useState, type FormEvent } from 'react';
import { isAxiosError } from 'axios';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { confirmReceiptExtraction, getReceipt, type ReceiptProcessingApi, type ReceiptReview, type ReviewedItem, type ReceiptDetails } from '../../api/receipts';
import { PageHeader } from '../../components/PageHeader';
import { ReceiptPreview } from '../../components/ReceiptPreview';
import '../../styles/receipt-review.css';
import {apiClient} from '../../api/client';

const textKeys = ['vendor','branch','business_number'] as const;
const moneyLabels: Record<string,string> = {payment_amount:'결제액',supply_amount:'공급가액',vat_amount:'부가세',tax_exempt_amount:'면세금액',discount_amount:'할인액',printed_total_amount:'인쇄 합계',subtotal_amount:'소계',taxable_supply_amount:'과세 공급가액'};
type DraftItem = Omit<ReviewedItem,'quantity'|'unit_price'|'line_amount'> & {quantity:string;unit_price:string;line_amount:string};
const blankItem = (): DraftItem => ({name:'',raw_name:null,source_row:null,quantity:'',unit_price:'',line_amount:'',row_type:'item',parent_row:null});
const numberOrNull = (value:string) => value.trim()==='' ? null : Number(value);

export function OcrExtractionReviewPage() {
  const {id}=useParams(); const navigate=useNavigate();
  const [search,setSearch]=useSearchParams();const detailed=search.get('view')==='all';
  const [answers,setAnswers]=useState<Record<string,string>>({});
  const [questions,setQuestions]=useState<Array<{id:string;label:string;options:Array<{value:string;label:string}>}>>([]);
  const [profileComplete,setProfileComplete]=useState(true);
  const [questionError,setQuestionError]=useState('');
  const [receipt,setReceipt]=useState<ReceiptProcessingApi|null>(null);
  const [fields,setFields]=useState<Record<string,string>>({});
  const [date,setDate]=useState(''); const [time,setTime]=useState('');
  const [items,setItems]=useState<DraftItem[]>([]);
  const [extraDetails,setExtraDetails]=useState<ReceiptDetails>({});
  const [purpose,setPurpose]=useState('');
  const [evidence,setEvidence]=useState<ReceiptReview['evidence_type']>('unknown');
  const [business,setBusiness]=useState('unknown');
  const [tax,setTax]=useState<ReceiptReview['tax_treatment']>('unknown');
  const [loading,setLoading]=useState(true); const [saving,setSaving]=useState(false);
  const [showAllItems,setShowAllItems]=useState(false);
  const [dirty,setDirty]=useState(false); const [error,setError]=useState('');
  useEffect(()=>{
    let active=true;
    if(!id)return;
    getReceipt(Number(id)).then(r=>{
      if(!active)return;
      if (r.status !== 'done' && r.status !== 'needs_edit') throw Error('문서 인식이 끝난 뒤 결과를 수정할 수 있습니다.');
      const doc=r.review?.document ?? r.recognition?.document;
      const source=doc?.fields ?? {business_number:r.details?.business_number??null,supply_amount:r.details?.supply_amount??null,vat_amount:r.details?.vat_amount??null,tax_exempt_amount:r.details?.tax_free_amount??null};
      const draft:Record<string,string>={};
      [...textKeys,...Object.keys(moneyLabels)].forEach(k=>draft[k]=source[k]==null?'':String(source[k]));
      draft.vendor=r.vendor??draft.vendor??'';
      draft.payment_amount=r.recognition?.document ? (source.payment_amount==null?'':String(source.payment_amount)) : (r.amount==null?draft.payment_amount:String(r.amount));
      const dt=String(source.transaction_datetime??'').replace('T',' ');
      setDate(r.date??dt.slice(0,10));setTime(dt.match(/\d{2}:\d{2}(?::\d{2})?/)?.[0]??'');
      setFields(draft);setItems((doc?.items??(r.details?.items??[]).map(i=>({name:i.name,raw_name:null,source_row:null,quantity:i.quantity,unit_price:i.unit_price,line_amount:i.amount,row_type:'item',parent_row:null}))).map((i,idx)=>({...i,raw_name:i.raw_name===undefined?i.name:i.raw_name,source_row:i.source_row===undefined?(r.review?.document?undefined:idx):i.source_row,quantity:i.quantity==null?'':String(i.quantity),unit_price:i.unit_price==null?'':String(i.unit_price),line_amount:i.line_amount==null?'':String(i.line_amount)})));
      setExtraDetails(r.details??{});
      setAnswers(r.review?.question_answers??{});setPurpose(r.review?.purpose??'');setEvidence(r.review?.evidence_type??'unknown');
      setBusiness(r.review?.business_related==null?'unknown':r.review.business_related?'yes':'no');setTax(r.review?.tax_treatment??'unknown');
      setReceipt(r);setDirty(false);
    }).catch(e=>{if(active)setError(e instanceof Error?e.message:'결과를 불러오지 못했습니다.');}).finally(()=>{if(active)setLoading(false);});
    return()=>{active=false;};
  },[id]);
  useEffect(()=>{if(!receipt)return;let active=true;apiClient.post(`/v2/receipts/${receipt.id}/questions`,answers).then(r=>{if(active){setQuestions(r.data.questions);if(JSON.stringify(r.data.answers)!==JSON.stringify(answers))setAnswers(r.data.answers);setProfileComplete(r.data.profile_complete);setQuestionError('');}}).catch(()=>{if(active)setQuestionError('거래 질문을 불러오지 못했습니다. 상세 정보에 용도를 입력해 주세요.');});return()=>{active=false;};},[receipt,answers]);
  useEffect(()=>{const warn=(e:BeforeUnloadEvent)=>{if(dirty){e.preventDefault();e.returnValue='';}};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);},[dirty]);
  const editField=(key:string,value:string)=>{setFields(v=>({...v,[key]:value}));setDirty(true);};
  const editItem=(index:number,patch:Partial<DraftItem>)=>{setItems(v=>v.map((item,i)=>i===index?{...item,...patch}:item));setDirty(true);};
  const removeItem=(index:number)=>{setItems(v=>v.filter((_,i)=>i!==index).map(item=>({...item,parent_row:item.parent_row===null?null:item.parent_row===index?null:item.parent_row>index?item.parent_row-1:item.parent_row})));setDirty(true);};
  function money(key:string){return <label className="review-field" key={key} htmlFor={`review-${key}`}><span>{moneyLabels[key]} (원)</span><input className="input" id={`review-${key}`} type="number" step="1" inputMode="numeric" value={fields[key]??''} placeholder="미확인" onChange={e=>editField(key,e.target.value)} required={key==='payment_amount'} />{receipt?.recognition?.document?.conflicts.includes(key)&&<small>사진에서 금액을 확인해 주세요.</small>}</label>;}
  async function save(e:FormEvent){
    e.preventDefault();if(!receipt||saving)return;
    setError('');
    const amount=numberOrNull(fields.payment_amount??'');
    if(!fields.vendor?.trim()||!date||amount===null||!Number.isSafeInteger(amount)||amount<0){setError('거래처·거래일·결제액을 확인해 주세요.');setSearch({view:'all'});return;}
    const corrected:Record<string,string|number|null>={};
    textKeys.forEach(k=>corrected[k]=fields[k]?.trim()||null);
    for(const key of Object.keys(moneyLabels)){
      const n=numberOrNull(fields[key]??'');
      if(n!==null&&!Number.isSafeInteger(n)){setError(`${moneyLabels[key]}를 원 단위 숫자로 입력해 주세요.`);return;}
      corrected[key]=n;
    }
    corrected.transaction_datetime=date+(time?' '+time:'');
    if(items.some(i=>i.source_row===undefined)){setError('기존 품목의 원본 연결을 상세 화면에서 확인해 주세요.');setSearch({view:'all'});return;}
    const converted:ReviewedItem[]=[];
    for(const [i,item] of items.entries()){
      if(!item.name.trim()){setError(`${i+1}번째 품목명을 입력하거나 해당 행을 삭제해 주세요.`);return;}
      const q=numberOrNull(item.quantity),u=numberOrNull(item.unit_price),p=numberOrNull(item.line_amount);
      if([q,u,p].some(n=>n!==null&&!Number.isFinite(n))){setError(`${i+1}번째 품목의 숫자를 확인해 주세요.`);return;}
      converted.push({...item,name:item.name.trim(),raw_name:item.raw_name??null,source_row:item.source_row,quantity:q,unit_price:u,line_amount:p});
    }
    setSaving(true);
    try{
      await confirmReceiptExtraction(receipt.id,{vendor:fields.vendor.trim(),amount,date,document:{fields:corrected,items:converted},details:extraDetails,question_answers:answers,purpose:purpose.trim()||null,evidence_type:evidence,business_related:business==='unknown'?null:business==='yes',tax_treatment:tax});
      setDirty(false);navigate(`/storage/${receipt.direction}`,{replace:true});
    }catch(e){const message=isAxiosError(e)?e.response?.data?.error?.message:null;setError(message??'수정 내용을 저장하지 못했습니다. 입력값은 유지됩니다.');}
    finally{setSaving(false);}
  }
  function retake(){if(!dirty||window.confirm('수정한 내용이 아직 저장되지 않았습니다. 다시 촬영할까요?'))navigate(`/capture?direction=${receipt?.direction??'purchase'}`);}
  return <div className="page receipt-review-page">
    <PageHeader title={detailed?"전체 정보 확인":"추출 결과 확인"} />
    <div className="page__body review-body">
      {loading?<p role="status">결과를 불러오는 중입니다.</p>:receipt?<div className="review-layout">
        <aside className="review-photo"><ReceiptPreview id={receipt.id} controls /></aside>
        <form className="review-form" onSubmit={e=>void save(e)}>
          {error&&<div className="review-error" role="alert">{error}</div>}
          <fieldset disabled={saving}>
            {!detailed&&<section className="review-section"><h2>영수증 정보</h2><div className="review-grid">
              <label className="review-field review-full"><span>공급자 상호</span><input className="input" value={fields.vendor??''} required onChange={e=>editField('vendor',e.target.value)}/></label>
              <label className="review-field review-full"><span>공급자 사업자등록번호</span><input className="input" value={fields.business_number??''} placeholder="미확인" onChange={e=>editField('business_number',e.target.value)}/></label>
              <div className="review-field review-full"><span>품목</span><div className="basic-item-names">{items.slice(0,showAllItems?items.length:3).map((item,i)=><label className="basic-item-name" key={i}><span>{i+1}</span><input aria-label={`품목 ${i+1} 이름`} className="input" value={item.name} maxLength={500} required placeholder="사진에 인쇄된 품목명" onChange={e=>editItem(i,{name:e.target.value})}/></label>)}</div>{items.length===0&&<p className="muted">읽은 품목이 없습니다. 전체 정보에서 추가할 수 있습니다.</p>}{items.length>3&&<button type="button" className="text-link" onClick={()=>setShowAllItems(v=>!v)}>{showAllItems?'품목 접기':`나머지 ${items.length-3}개 품목 수정`}</button>}<button type="button" className="text-link" onClick={()=>setSearch({view:'all'})}>수량·금액·할인 수정</button></div>
              {money('supply_amount')}{money('vat_amount')}
              <label className="review-field review-full"><span>발행·거래 날짜</span><input className="input" type="date" value={date} required onChange={e=>{setDate(e.target.value);setDirty(true);}}/></label>
            </div><button type="button" className="btn btn--secondary" onClick={()=>setSearch({view:'all'})}>전체 정보 확인</button></section>}
            {!detailed&&receipt.direction==='purchase'&&<section className="review-section"><h2>사용 목적 확인</h2>{!profileComplete&&<p>공제 분석에 필요한 사업 정보를 입력해 주세요. <a href="/account">사업 정보 입력</a></p>}{questionError&&<p role="alert">{questionError}</p>}{questions.map(q=><label className="review-field" key={q.id}><span>{q.label}</span><select aria-label={q.label} className="input" value={answers[q.id]??''} onChange={e=>{setAnswers(v=>q.id===questions[0]?.id?{[q.id]:e.target.value}:{...v,[q.id]:e.target.value});setDirty(true);}}><option value="">나중에 확인</option>{q.options.map(o=><option key={o.value} value={o.value}>{o.label}</option>)}</select></label>)}{Object.values(answers).includes('other')&&<label className="review-field"><span>실제 사용 상황</span><textarea aria-label="실제 사용 상황" className="input review-purpose" value={answers.detail??''} maxLength={1000} placeholder="누가, 무엇을 위해 사용했는지 간단히 적어 주세요." onChange={e=>{setAnswers(v=>({...v,detail:e.target.value}));setDirty(true);}}/></label>}<p className="muted">공제 여부가 아니라 실제 사용 상황을 알려 주세요. 아직 모르면 저장 후 답변할 수 있습니다.</p></section>}
            {detailed&&<><button type="button" className="text-link" onClick={()=>setSearch({})}>← 기본 정보로 돌아가기</button>
            <section className="review-section"><h2>거래 정보</h2><div className="review-grid">
              <label className="review-field review-full" htmlFor="review-vendor"><span>거래처</span><input id="review-vendor" className="input" value={fields.vendor??''} required maxLength={255} onChange={e=>editField('vendor',e.target.value)} /></label>
              <label className="review-field" htmlFor="review-branch"><span>지점</span><input id="review-branch" className="input" value={fields.branch??''} placeholder="미확인" maxLength={255} onChange={e=>editField('branch',e.target.value)} /></label>
              <label className="review-field" htmlFor="review-business_number"><span>판매자 사업자등록번호</span><input id="review-business_number" className="input" value={fields.business_number??''} placeholder="미확인" maxLength={30} onChange={e=>editField('business_number',e.target.value)} /></label>
              <label className="review-field" htmlFor="review-date"><span>거래일</span><input id="review-date" type="date" className="input" value={date} required onChange={e=>{setDate(e.target.value);setDirty(true);}} /></label>
              <label className="review-field" htmlFor="review-time"><span>거래 시간</span><input id="review-time" type="time" step="1" className="input" value={time} onChange={e=>{setTime(e.target.value);setDirty(true);}} /></label>
              {money('payment_amount')}
            </div></section>
            <section className="review-section"><h2>세금·금액</h2><div className="review-grid">{['supply_amount','vat_amount','tax_exempt_amount','discount_amount'].map(money)}</div><details className="review-more"><summary>그 외 금액</summary><div className="review-grid">{['printed_total_amount','subtotal_amount','taxable_supply_amount'].map(money)}</div></details></section>
            <section className="review-section"><h2>증빙 정보</h2><label className="review-field" htmlFor="review-purpose"><span>거래 목적</span><textarea aria-label="거래 목적" id="review-purpose" className="input review-purpose" value={purpose} maxLength={1000} placeholder="예: 매장 운영용 물품 구매" onChange={e=>{setPurpose(e.target.value);setDirty(true);}} /></label>
              <div className="review-grid"><label className="review-field" htmlFor="review-evidence"><span>증빙 종류</span><select aria-label="증빙 종류" id="review-evidence" className="input" value={evidence} onChange={e=>{setEvidence(e.target.value as ReceiptReview['evidence_type']);setDirty(true);}}><option value="unknown">확인 안 함</option><option value="card_receipt">카드 영수증</option><option value="cash_receipt">현금영수증</option><option value="tax_invoice">세금계산서</option><option value="tax_free_receipt">면세 증빙</option><option value="manual">수기 증빙</option></select></label>
              <label className="review-field" htmlFor="review-business"><span>사업 관련 지출</span><select aria-label="사업 관련 지출" id="review-business" className="input" value={business} onChange={e=>{setBusiness(e.target.value);setDirty(true);}}><option value="unknown">확인 안 함</option><option value="yes">예</option><option value="no">아니요</option></select></label>
              <label className="review-field" htmlFor="review-tax"><span>과세 구분</span><select aria-label="과세 구분" id="review-tax" className="input" value={tax} onChange={e=>{setTax(e.target.value as ReceiptReview['tax_treatment']);setDirty(true);}}><option value="unknown">확인 안 함</option><option value="standard">과세</option><option value="zero">영세율</option><option value="exempt">면세</option></select></label></div>
            </section>
<section className="review-section"><div className="review-section-heading"><h2>품목</h2><button type="button" className="review-add" onClick={()=>{setItems(v=>[...v,blankItem()]);setDirty(true);}}>+ 품목 추가</button></div>
              {items.length===0&&<p className="review-empty">필요한 품목을 추가할 수 있습니다.</p>}
              {items.map((item,i)=><div className="review-item" key={i}>
                {item.source_row===undefined&&<label className="review-field"><span>원본 품목 연결 확인</span><select className="input" required value="" onChange={e=>editItem(i,{source_row:e.target.value==='new'?null:Number(e.target.value)})}><option value="">원본을 선택해 주세요</option><option value="new">사용자가 추가한 품목</option>{(receipt.recognition?.original_document?.items??receipt.recognition?.document?.items??[]).map((o,j)=><option key={j} value={j}>{j+1}. {o.name}</option>)}</select></label>}<div className="review-item-heading"><span>{i+1}</span><button type="button" aria-label={`${i+1}번째 품목 삭제`} onClick={()=>removeItem(i)}>삭제</button></div>
                <label className="review-field" htmlFor={`item-${i}-name`}><span>품목명</span><input id={`item-${i}-name`} className="input" value={item.name} maxLength={500} required onChange={e=>editItem(i,{name:e.target.value})} />{item.raw_name&&item.raw_name!==item.name&&<small>모델 원출력 이름: {item.raw_name}</small>}</label>
                <div className="review-item-numbers">{(['quantity','unit_price','line_amount'] as const).map((key,index)=><label className="review-field" key={key} htmlFor={`item-${i}-${key}`}><span>{['수량','단가 (원)','행 금액 (원)'][index]}</span><input id={`item-${i}-${key}`} type="number" step={key==='quantity'?'any':'1'} className="input" value={item[key]} placeholder="미확인" onChange={e=>editItem(i,{[key]:e.target.value})} /></label>)}</div>
                <div className="review-grid"><label className="review-field" htmlFor={`item-${i}-type`}><span>행 구분</span><select id={`item-${i}-type`} className="input" value={item.row_type} onChange={e=>{const type=e.target.value as ReviewedItem['row_type'];setItems(v=>v.map((r,j)=>j===i?{...r,row_type:type,parent_row:null}:r.parent_row===i?{...r,parent_row:null}:r));setDirty(true);}}><option value="item">상품</option><option value="option">옵션</option><option value="discount">할인</option></select></label>
                {item.row_type!=='item'&&<label className="review-field" htmlFor={`item-${i}-parent`}><span>연결 상품</span><select id={`item-${i}-parent`} className="input" value={item.parent_row??''} onChange={e=>editItem(i,{parent_row:e.target.value===''?null:Number(e.target.value)})}><option value="">연결 없음</option>{items.map((r,j)=>r.row_type==='item'&&j!==i?<option key={j} value={j}>{j+1}. {r.name||'품목명 미입력'}</option>:null)}</select></label>}</div>
              </div>)}
            </section>

            <section className="review-section"><h2>추가 증빙 정보</h2><div className="review-grid">{([['address','사업장 주소'],['phone','전화번호'],['payment_method','결제수단'],['approval_number','승인번호'],['receipt_number','영수증·문서번호']] as const).map(([key,label])=><label className="review-field" key={key}><span>{label}</span><input className="input" maxLength={key==='address'?300:key==='receipt_number'?60:40} value={extraDetails[key]??''} placeholder="미확인" onChange={e=>{setExtraDetails(v=>({...v,[key]:e.target.value||null}));setDirty(true);}}/></label>)}</div>
            {(extraDetails.additional_fields??[]).map((row,i)=><div className="review-grid" key={i}><label className="review-field"><span>항목명</span><input className="input" maxLength={100} value={row.label} onChange={e=>{setExtraDetails(v=>({...v,additional_fields:v.additional_fields?.map((a,j)=>j===i?{...a,label:e.target.value}:a)}));setDirty(true);}}/></label><label className="review-field"><span>내용</span><input className="input" maxLength={1000} value={row.value} onChange={e=>{setExtraDetails(v=>({...v,additional_fields:v.additional_fields?.map((a,j)=>j===i?{...a,value:e.target.value}:a)}));setDirty(true);}}/></label><button type="button" className="text-link" onClick={()=>{setExtraDetails(v=>({...v,additional_fields:v.additional_fields?.filter((_,j)=>i!==j)}));setDirty(true);}}>추가 항목 삭제</button></div>)}
            <button type="button" className="text-link" disabled={(extraDetails.additional_fields?.length??0)>=50} onClick={()=>{setExtraDetails(v=>({...v,additional_fields:[...(v.additional_fields??[]),{label:'',value:''}]}));setDirty(true);}}>+ 추가 정보 입력</button></section>
            </>}
          </fieldset>
          <div className="review-actions"><button type="submit" className="btn btn--primary" disabled={saving}>{saving?'저장 중…':'저장하고 보관함으로'}</button><button type="button" className="review-retake" disabled={saving} onClick={retake}>다시 촬영</button></div>
        </form>
      </div>:<div className="review-error" role="alert">{error}</div>}
    </div>
  </div>;
}
