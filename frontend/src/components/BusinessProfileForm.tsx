import {useEffect,useState} from 'react';
import {apiClient} from '../api/client';
type Profile={business_name:string|null;business_number:string|null;verified_tax_type:string|null;verification_status:string;declared_tax_type:string|null;entity_type:string|null;operating_industry:string|null;business_description:string|null;has_employees:boolean|null;onboarding_completed:boolean};
export function BusinessProfileForm(){
 const [p,setP]=useState<Profile|null>(null),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{apiClient.get<Profile>('/v2/business/profile').then(r=>setP(r.data)).catch(()=>setMessage('사업 정보를 불러오지 못했습니다.'));},[]);
 async function save(){if(!p)return;setBusy(true);setMessage('');try{const {data}=await apiClient.put<Profile>('/v2/business/profile',{business_name:p.business_name,declared_tax_type:p.declared_tax_type,entity_type:p.entity_type,operating_industry:p.operating_industry,business_description:p.business_description,has_employees:p.has_employees});setP(data);setMessage(data.onboarding_completed?'사업 정보를 저장했습니다.':'저장했습니다. 미입력 정보는 나중에 확인해 주세요.');}catch{setMessage('사업 정보를 저장하지 못했습니다. 입력값을 확인해 주세요.');}finally{setBusy(false);}}
 function update(key:keyof Profile,value:unknown){setP(v=>v?{...v,[key]:value}:v);}
 return <section className="review-section business-profile-form"><h2>내 사업 프로필</h2><p className="muted">거래 용도를 확인할 때 사용하는 정보입니다. 변경하면 기존 공제 분석을 다시 확인합니다.</p>{message&&<p role="status">{message}</p>}{p&&<fieldset disabled={busy}>
 <label className="review-field"><span>상호</span><input className="input" value={p.business_name??''} onChange={e=>update('business_name',e.target.value)}/></label>
 <p>사업자등록번호: {p.business_number??'미확인'}</p><p className="muted">조회된 과세 유형: {p.verified_tax_type??'미확인'}</p>
 <label className="review-field"><span>현재 과세 유형</span><select className="input" value={p.declared_tax_type??''} onChange={e=>update('declared_tax_type',e.target.value||null)}><option value="">미확인</option><option value="general">일반과세</option><option value="simplified">간이과세</option><option value="exempt">면세사업</option></select></label>
 <label className="review-field"><span>사업자 형태가 어떻게 되나요?</span><select aria-label="사업자 형태가 어떻게 되나요?" className="input" value={p.entity_type??''} onChange={e=>update('entity_type',e.target.value||null)}><option value="">아직 확인하지 못함</option><option value="individual">개인사업자</option><option value="corporation">법인사업자</option></select></label>
 <label className="review-field"><span>실제 업종</span><select className="input" value={p.operating_industry??''} onChange={e=>update('operating_industry',e.target.value||null)}><option value="">미확인</option>{[['food_service','음식점'],['cafe','카페·베이커리'],['retail','도소매'],['manufacturing','제조업'],['service','서비스업'],['other','기타']].map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label>
 <label className="review-field"><span>실제 하는 일</span><textarea className="input" maxLength={1000} placeholder="예: 동네 카페 운영" value={p.business_description??''} onChange={e=>update('business_description',e.target.value||null)}/></label>
 <label className="review-field"><span>직원 유무</span><select className="input" value={p.has_employees===null?'':p.has_employees?'yes':'no'} onChange={e=>update('has_employees',e.target.value===''?null:e.target.value==='yes')}><option value="">미확인</option><option value="yes">직원 있음</option><option value="no">직원 없음</option></select></label>
 <button type="button" className="btn btn--primary" onClick={()=>void save()}>{busy?'저장 중…':'사업 프로필 저장'}</button>
 </fieldset>}</section>;
}
