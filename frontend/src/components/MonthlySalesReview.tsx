import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { PageHeader } from "./PageHeader";
import "../styles/monthly-sales.css";

type Values = Record<string, string | number | null>;
export type MonthlyDocument = { 사업장: Values; 거래일: string | null; 집계합계: Values; 매출집계_유형별: Values[]; 세무조정_필수항목: Values };
export type SavedDocument = { id: number; status: string; created_at: string; document: MonthlyDocument; raw_prediction: MonthlyDocument; warnings: string[] };
const numeric = new Set(["총판매액","총할인액","취소환불액","실매출액","과세공급가액","부가세합계","면세매출액","합계금액","공급가액","부가세","할인액","포인트사용액","현금영수증발행액"]);

function Fields({ values, onChange }: { values: Values; onChange: (name: string, value: string | number | null) => void }) {
  return <div className="monthly-sales__fields">{Object.entries(values).map(([name, value]) => <label key={name}><span>{name}</span>
    {name === "결제수단" || name === "과세구분" ? <select value={value ?? ""} onChange={e => onChange(name,e.target.value || null)}><option value="">확인 필요</option>{(name === "결제수단" ? ["카드","현금","간편결제","계좌이체","포인트","기타"] : ["과세","면세","영세율"]).map(v=><option key={v}>{v}</option>)}</select> :
    <input aria-label={name} type={numeric.has(name) ? "number" : "text"} inputMode={numeric.has(name) ? "numeric" : undefined} value={value ?? ""} placeholder="확인 필요" onChange={e => onChange(name, e.target.value === "" ? null : numeric.has(name) ? Number(e.target.value) : e.target.value)} />}
  </label>)}</div>;
}

export function MonthlySalesReviewPage() {
  const {id}=useParams();const navigate=useNavigate();
  const [result,setResult]=useState<SavedDocument|null>(null); const [image,setImage]=useState("");
  const [busy,setBusy]=useState(false); const [error,setError]=useState("");
  useEffect(()=>{let active=true; apiClient.get<SavedDocument>(`/sales/monthly/${id}`).then(({data})=>{if(active)setResult(data);}).catch(()=>{if(active)setError("정산서를 불러오지 못했습니다.");});return()=>{active=false;};},[id]);
  useEffect(()=>{
    if(!result) { setImage(""); return; }
    setImage("");
    let active=true; let url="";
    apiClient.get<Blob>(`/sales/monthly/${result.id}/image`,{responseType:"blob"}).then(r=>{if(active){url=URL.createObjectURL(r.data);setImage(url);}}).catch(()=>{if(active)setError("원본 사진을 불러오지 못했습니다.");});
    return ()=>{active=false;if(url)URL.revokeObjectURL(url);};
  },[result?.id]);
  function update(section: keyof MonthlyDocument, name:string, value:string|number|null, index?:number) {
    setResult(current=>{if(!current)return current;const document=structuredClone(current.document);
      if(section === "거래일") document.거래일=value == null ? null : String(value);
      else if(section === "매출집계_유형별" && index != null) document.매출집계_유형별[index][name]=value;
      else if(section !== "매출집계_유형별") (document[section] as Values)[name]=value;
      return {...current,document};});
  }
  function changeRows(index?:number){setResult(current=>{if(!current)return current;const document=structuredClone(current.document);if(index === undefined)document.매출집계_유형별.push({원문항목:"",결제수단:null,과세구분:null,합계금액:null,공급가액:null,부가세:null});else document.매출집계_유형별.splice(index,1);return {...current,document};});}
  async function save(){if(!result||busy)return;setBusy(true);setError("");try{await apiClient.put(`/sales/monthly/${result.id}/review`,{document:result.document});navigate('/storage/sales',{replace:true});}catch{setError("수정 내용을 저장하지 못했습니다. 입력값을 확인해 주세요.");}finally{setBusy(false);}}
  return <div className="page qa-page"><PageHeader title="매출 증빙 확인" onBack={()=>navigate('/storage/sales')}/><main className="page__body"><section className="card monthly-sales" aria-labelledby="monthly-sales-title">
    <p className="eyebrow muted">월간 매출 정산서</p><h1 id="monthly-sales-title" className="section-title">추출 결과 확인</h1>
    {busy&&<p role="status">저장하고 있어요.</p>}{error&&<p className="banner banner--info" role="alert">{error}</p>}
    {result&&<div className="monthly-sales__result"><p className="banner banner--info">원본과 비교해 수정한 뒤 저장해 주세요. 월간 집계는 개별 거래와 별도로 보관합니다.</p>
      {result.warnings.map(w=><p className="banner banner--info" key={w}>{w}</p>)}
      {image&&<details><summary>원본 사진 보기</summary><img className="monthly-sales__image" src={image} alt="업로드한 매출 정산서 원본" /></details>}
      <h3>사업장</h3><Fields values={result.document.사업장} onChange={(n,v)=>update("사업장",n,v)} />
      <h3>기간</h3><Fields values={{거래월:result.document.거래일}} onChange={(n,v)=>update("거래일",n,v)} />
      <h3>매출 합계</h3><Fields values={result.document.집계합계} onChange={(n,v)=>update("집계합계",n,v)} />
      <h3>결제수단별 내역</h3>{result.document.매출집계_유형별.length?result.document.매출집계_유형별.map((row,i)=><div className="monthly-sales__row" key={i}><Fields values={row} onChange={(n,v)=>update("매출집계_유형별",n,v,i)} /><button type="button" className="btn btn--ghost btn--sm" onClick={()=>changeRows(i)}>이 행 삭제</button></div>):<p className="muted">확인된 결제수단별 내역이 없습니다.</p>}
      <button type="button" className="btn btn--ghost btn--sm" onClick={()=>changeRows()}>결제수단 행 추가</button>
      <h3>조정 항목</h3><Fields values={result.document.세무조정_필수항목} onChange={(n,v)=>update("세무조정_필수항목",n,v)} />
      <button type="button" className="btn btn--primary" disabled={busy} onClick={()=>void save()}>확인 내용 저장</button>
    </div>}
  </section></main></div>;
}
